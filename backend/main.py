"""
Task App Backend - 老江湖的任务管理系统
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os, sqlite3
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import feedparser

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'tasks.db')

# ========== 数据库初始化 ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        color TEXT DEFAULT '#4a9eff',
        completed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        link TEXT,
        source TEXT,
        summary TEXT,
        fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
        batch INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

# ========== 新闻爬虫 ==========
def fetch_news():
    """每天4个时间点抓取新闻，INSERT模式，总量上限40条"""
    rss_feeds = [
        ('36氪', 'https://36kr.com/feed'),
        ('人民日报', 'http://www.people.com.cn/rss/politics.xml'),
        ('新浪新闻', 'http://rss.sina.com.cn/news/china/focus15.xml'),
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    # 获取当前批次号（当天最大批次，最大为4）
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(MAX(batch), 0)
        FROM news
        WHERE date(fetched_at) = date('now')
    """)
    today_max_batch = c.fetchone()[0]
    new_batch = (today_max_batch % 4) + 1  # 0->1->2->3->4->1循环
    conn.close()

    count = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for name, url in rss_feeds:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:10]:
                title = entry.get('title', '').strip()
                link = entry.get('link', '#') or '#'
                summary = entry.get('summary', entry.get('description', ''))
                import re
                summary = re.sub(r'<[^>]+>', '', summary).strip()[:200]
                if title:
                    c.execute(
                        'INSERT INTO news (title, link, source, summary, batch) VALUES (?, ?, ?, ?, ?)',
                        (title, link, name, summary, new_batch)
                    )
                    count += 1
        except Exception as e:
            print(f"[News] Failed {name}: {e}")

    conn.commit()
    conn.close()
    trim_news()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Batch {new_batch}: fetched {count} news")
    return count

def trim_news():
    """FIFO：只保留最新40条"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id FROM news ORDER BY id DESC')
    all_ids = [row[0] for row in c.fetchall()]
    if len(all_ids) > 40:
        to_delete = all_ids[40:]
        placeholders = ','.join('?' * len(to_delete))
        c.execute(f'DELETE FROM news WHERE id IN ({placeholders})', to_delete)
        conn.commit()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] FIFO: deleted {len(to_delete)}, kept 40")
    conn.close()

# ========== 任务 API ==========
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM tasks ORDER BY created_at DESC')
    tasks = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(tasks)

@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.json
    title = data.get('title', '').strip()
    color = data.get('color', '#4a9eff')
    if not title:
        return jsonify({'error': '标题不能为空'}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO tasks (title, color) VALUES (?, ?)', (title, color))
    task_id = c.lastrowid
    conn.commit()
    c.execute('SELECT id, title, color, completed, created_at, completed_at FROM tasks WHERE id=?', (task_id,))
    row = c.fetchone()
    task = {'id':row[0],'title':row[1],'color':row[2],'completed':row[3],'created_at':row[4],'completed_at':row[5]}
    conn.close()
    return jsonify(task), 201

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if 'completed' in data:
        completed = 1 if data['completed'] else 0
        completed_at = datetime.now().isoformat() if completed else None
        c.execute('UPDATE tasks SET completed=?, completed_at=? WHERE id=?', (completed, completed_at, task_id))
    if 'color' in data:
        c.execute('UPDATE tasks SET color=? WHERE id=?', (data['color'], task_id))
    if 'title' in data:
        c.execute('UPDATE tasks SET title=? WHERE id=?', (data['title'], task_id))
    conn.commit()
    c.execute('SELECT id, title, color, completed, created_at, completed_at FROM tasks WHERE id=?', (task_id,))
    row = c.fetchone()
    task = {'id':row[0],'title':row[1],'color':row[2],'completed':row[3],'created_at':row[4],'completed_at':row[5]}
    conn.close()
    return jsonify(task)

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/tasks/clear-completed', methods=['DELETE'])
def clear_completed():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM tasks WHERE completed=1')
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ========== 新闻 API ==========
@app.route('/api/news', methods=['GET'])
def get_news():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # 只取最近7天的新闻，按时间倒序
    c.execute("""
        SELECT * FROM news
        WHERE fetched_at >= datetime('now', '-7 days')
        ORDER BY fetched_at DESC
    """)
    news = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(news)

@app.route('/api/news/latest', methods=['GET'])
def get_latest_batch():
    """只返回最近一批抓取的10条新闻（用于顶部滚动）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM news
        WHERE fetched_at >= datetime('now', '-7 days')
        ORDER BY batch DESC, fetched_at DESC
        LIMIT 10
    """)
    news = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(news)

@app.route('/api/news/refresh', methods=['POST'])
def refresh_news():
    n = fetch_news()
    return jsonify({'fetched': n})

# ========== 定时任务 ==========
def daily_reset():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 执行每日任务清空...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM tasks')
    conn.commit()
    conn.close()

def init_scheduler():
    scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
    scheduler.add_job(daily_reset, 'cron', hour=3, minute=0, id='daily_reset')
    for hour in [8, 12, 16, 20]:
        scheduler.add_job(fetch_news, 'cron', hour=hour, minute=0, id=f'news_{hour}')
    fetch_news()  # 启动时抓一次
    scheduler.start()
    print("[Scheduler] 启动 | 任务清空:03:00 | 新闻抓取:08:00/12:00/16:00/20:00")

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

init_db()
init_scheduler()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
