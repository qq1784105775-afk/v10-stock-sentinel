import os
import sys
import tarfile
import glob
import time
import sqlite3

BASE_DIR = "/www/wwwroot/v9_upgrade"
MAIN_PY = os.path.join(BASE_DIR, "main.py")

print("========================================")
print("🚑 启动 V36 救援程序 (回滚 & 修复)")
print("========================================")

# 1. 寻找刚才 V34 生成的自动备份
print(">> [1/4] 正在寻找救命备份文件...")
backups = glob.glob("/www/wwwroot/backup_before_v34_*.tar.gz")
if not backups:
    # 如果没找到 V34 备份，尝试找更早的
    backups = glob.glob("/www/wwwroot/v9_upgrade_backup_*.tar.gz")

if not backups:
    print("❌ 完蛋！找不到任何备份文件。请联系我手动处理。")
    sys.exit(1)

# 找最新的一个
latest_backup = max(backups, key=os.path.getctime)
print(f"   ✅ 找到备份: {latest_backup}")

# 2. 只从备份中恢复 main.py
print(">> [2/4] 正在恢复 main.py ...")
try:
    with tarfile.open(latest_backup, "r:gz") as tar:
        # 不同的备份打包路径可能不同，尝试寻找 main.py
        member = None
        for m in tar.getmembers():
            if m.name.endswith("main.py"):
                member = m
                break
        
        if member:
            # 提取并覆盖
            f = tar.extractfile(member)
            content = f.read()
            with open(MAIN_PY, "wb") as out:
                out.write(content)
            print("   ✅ main.py 已恢复为纯净版本！")
        else:
            print("❌ 备份里居然没有 main.py？")
            sys.exit(1)
except Exception as e:
    print(f"❌ 恢复失败: {e}")
    sys.exit(1)

# 3. 植入绝对安全的“直连数据库”补丁
print(">> [3/4] 正在植入防 500 补丁...")

# 这是一个完全独立的补丁块，放在文件末尾最安全
PATCH_CODE = """
# [V36_SAFE_PATCH]
import sqlite3

# 强制覆盖旧路由，不依赖任何外部变量
@app.get("/api/watchlist")
def get_watchlist_v36():
    try:
        # 直连数据库文件，绝不报错
        conn = sqlite3.connect('/www/wwwroot/v9_upgrade/v8_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT ts_code, name FROM watchlist")
        rows = cursor.fetchall()
        conn.close()
        
        result = [{"ts_code": r[0], "name": r[1]} for r in rows]
        return {"success": True, "stocks": result}
    except Exception as e:
        print(f"DB Error: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/positions")
def get_positions_v36():
    try:
        conn = sqlite3.connect('/www/wwwroot/v9_upgrade/v8_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions")
        cols = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        result = [dict(zip(cols, row)) for row in rows]
        return {"success": True, "positions": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
# [V36_SAFE_PATCH_END]
"""

with open(MAIN_PY, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 智能插入：找到启动入口，插在它前面
new_lines = []
inserted = False
for line in lines:
    if ('if __name__ == "__main__":' in line or "if __name__ == '__main__':" in line) and not inserted:
        new_lines.append(PATCH_CODE + "\n")
        inserted = True
    new_lines.append(line)

if not inserted:
    new_lines.append(PATCH_CODE)

with open(MAIN_PY, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("   ✅ 补丁植入完成。")

# 4. 重启服务
print(">> [4/4] 正在重启服务...")
os.system("pkill -f main.py")
os.system("pkill -f cloud_sentinel.py")
time.sleep(2)

os.system(f"nohup {BASE_DIR}/venv/bin/python {BASE_DIR}/main.py > /dev/null 2>&1 &")
time.sleep(3)
os.system(f"nohup {BASE_DIR}/venv/bin/python {BASE_DIR}/cloud_sentinel.py > sentinel.out 2>&1 &")

# 检查是否存活
check = os.popen("ps -ef | grep main.py | grep -v grep").read()
if check:
    print("\n🎉🎉🎉 救援成功！主程序已启动！")
    print("👉 请检查 API 是否正常返回数据。")
else:
    print("\n❌ 警告：主程序启动失败，请运行 './venv/bin/python main.py' 查看具体报错。")
