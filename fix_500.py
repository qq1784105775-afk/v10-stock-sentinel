import os
import sys

file_path = "/www/wwwroot/v9_upgrade/main.py"
print(f">> 正在修复 500 错误：{file_path} ...")

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1. 清理之前的 V34 API 代码
clean_lines = []
skip = False
for line in lines:
    if "def get_watchlist_v34" in line:
        skip = True
    if "def get_positions_v34" in line:
        skip = True
    
    # 如果遇到下一个装饰器或函数，停止跳过
    if skip and line.strip().startswith("@app."):
        skip = False
    
    if not skip:
        clean_lines.append(line)

# 2. 构造“直连数据库”的强力 API
# 直接引入 sqlite3，自己去读文件，不依赖外部变量
direct_api_code = """
import sqlite3

# [V35_DIRECT_FIX]
@app.get("/api/watchlist")
async def get_watchlist_direct():
    try:
        # 方案A: 尝试用全局变量 (如果运气好)
        if 'db' in globals():
            data = db.get_watchlist()
            return {"success": True, "stocks": [{"ts_code": x["ts_code"], "name": x["name"]} for x in data]}
    except:
        pass
    
    try:
        # 方案B: 自己动手，直连数据库文件 (必杀技)
        conn = sqlite3.connect('/www/wwwroot/v9_upgrade/v8_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT ts_code, name FROM watchlist")
        rows = cursor.fetchall()
        conn.close()
        
        # 手动拼装数据
        result = []
        for row in rows:
            result.append({"ts_code": row[0], "name": row[1]})
        return {"success": True, "stocks": result}
        
    except Exception as e:
        print(f"DB Error: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/positions")
async def get_positions_direct():
    try:
        # 直连查询持仓
        conn = sqlite3.connect('/www/wwwroot/v9_upgrade/v8_data.db')
        cursor = conn.cursor()
        # 获取列名
        cursor.execute("SELECT * FROM positions")
        cols = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            result.append(dict(zip(cols, row)))
        return {"success": True, "positions": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
# [V35_DIRECT_FIX_END]
"""

# 3. 插入代码 (找到启动入口前)
final_lines = []
inserted = False
for line in clean_lines:
    if ('if __name__ == "__main__":' in line or "if __name__ == '__main__':" in line) and not inserted:
        final_lines.append(direct_api_code + "\n")
        inserted = True
    final_lines.append(line)

if not inserted:
    final_lines.append(direct_api_code)

# 4. 写入
with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(final_lines)

print("✅ 修复完成！已切换为数据库直连模式。")
