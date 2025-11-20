import os
import sqlite3
import datetime
import logging
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("InventorySystem")

KEY_FILE_PATH = 'bold-tooling-466206-a9-960a00bb4c78.json'
SPREADSHEET_ID = '1U6_t-ZDf6_qAemvSdp7_PQ7qMdLpgzxLHCiKiueVqEg'
SHEET_NAME = 'Sheet1'
DB_FILE = "inventory_system.db"

def authenticate_service_account(json_keyfile_path):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = service_account.Credentials.from_service_account_file(
        json_keyfile_path, scopes=SCOPES)
    return creds

def create_sheets_service(creds):
    return build('sheets', 'v4', credentials=creds)

def read_sheet(service, spreadsheet_id, range_name):
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        values = result.get('values', [])
        if not values:
            logger.info('데이터가 없습니다.')
            return None
        return values
    except HttpError as err:
        logger.error(f'오류 발생: {err}')
        return None

def write_sheet(service, spreadsheet_id, range_name, values):
    try:
        body = {'values': values}
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        return result
    except HttpError as err:
        logger.error(f'오류 발생: {err}')
        return None

try:
    creds = authenticate_service_account(KEY_FILE_PATH)
    google_service = create_sheets_service(creds)
    logger.info("Google Sheets API Service Initialized.")
except Exception as e:
    logger.error(f"Failed to init Google Service: {e}")
    google_service = None

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, channel)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_id TEXT NOT NULL,
            user_id TEXT,
            item_name TEXT NOT NULL,
            delta_qty INTEGER NOT NULL,
            snapshot_qty INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

@mcp.tool(name="lookup_inventory")
def lookup_inventory(item_name: str) -> str:
    if not google_service: return "구글 서비스 연결 실패"
    
    values = read_sheet(google_service, SPREADSHEET_ID, f"{SHEET_NAME}!A:C")
    if not values: return "시트 데이터를 읽을 수 없습니다."

    for row in values:
        if len(row) > 0 and row[0] == item_name:
            qty = row[1] if len(row) > 1 else "0"
            return f"성공: {item_name} 수량은 {qty}개 입니다."
            
    return f"실패: 품목 '{item_name}'이(가) 시트에 존재하지 않습니다."

@mcp.tool(name="update_stock")
def update_stock(item_name: str, quantity: int) -> str:
    if not google_service: return "구글 서비스 연결 실패"

    values = read_sheet(google_service, SPREADSHEET_ID, f"{SHEET_NAME}!A:B")
    if not values: return "데이터 읽기 실패"

    target_row_index = -1
    current_qty = 0

    for i, row in enumerate(values):
        if len(row) > 0 and row[0] == item_name:
            target_row_index = i + 1
            current_qty = int(row[1]) if len(row) > 1 else 0
            break
    
    if target_row_index == -1:
        return f"실패: 품목 '{item_name}'이(가) 없습니다."

    new_qty = current_qty + quantity
    if new_qty < 0:
        return f"실패: 재고 부족 (현재: {current_qty}, 요청변동: {quantity})"

    range_name = f"{SHEET_NAME}!B{target_row_index}"
    result = write_sheet(google_service, SPREADSHEET_ID, range_name, [[new_qty]])
    
    if result:
        return f"성공: '{item_name}' 재고 변경 완료 ({current_qty} -> {new_qty})"
    else:
        return "실패: 시트 업데이트 중 오류 발생"

@mcp.tool(name="check_threshold")
def check_threshold(check_quantity: int) -> str:
    values = read_sheet(google_service, SPREADSHEET_ID, f"{SHEET_NAME}!A:B")
    if not values: return "데이터 읽기 실패"

    low_stock = []
    data_rows = values[1:] if values else []

    for row in data_rows:
        if len(row) >= 2:
            name = row[0]
            try:
                qty = int(row[1])
                if qty <= check_quantity:
                    low_stock.append(f"{name}({qty}개)")
            except ValueError:
                continue

    if not low_stock:
        return "성공: 기준치 미달 품목 없음."
    
    return f"성공(부족): {', '.join(low_stock)}"

@mcp.tool(name="forecast_depletion")
def forecast_depletion(item_name: str) -> str:
    res = lookup_inventory(item_name)
    if "실패" in res: return res
    
    import re
    match = re.search(r'(\d+)개', res)
    if not match: return "수량 파싱 실패"
    
    qty = int(match.group(1))
    daily_usage = 2
    
    if qty == 0: return "이미 소진됨"
    
    days = qty // daily_usage
    date = datetime.date.today() + datetime.timedelta(days=days)
    return f"성공: '{item_name}'은 {date}경 소진 예상 (현재 {qty}개)"

@mcp.tool(name="save_log")
def save_log(item_name: str, delta_qty: int, user_id: str = "system", snapshot_qty: int = None) -> str:
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO logs (sheet_id, user_id, item_name, delta_qty, snapshot_qty)
            VALUES (?, ?, ?, ?, ?)
        ''', (SPREADSHEET_ID, user_id, item_name, delta_qty, snapshot_qty))
        
        conn.commit()
        conn.close()
        return "성공: 로그 저장됨"
    except Exception as e:
        return f"실패: {e}"

@mcp.tool(name="register_user_sheet")
def register_user_sheet(user_id: str, channel: str, sheet_id: str) -> str:
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO users (user_id, channel, sheet_id) 
            VALUES (?, ?, ?)
        ''', (user_id, channel, sheet_id))
        
        conn.commit()
        conn.close()
        return f"성공: {user_id} ({channel}) 등록 완료."
        
    except sqlite3.IntegrityError:
        return "실패: 해당 채널에 이미 등록된 사용자 ID입니다."
    except Exception as e:
        return f"실패: {e}"

@mcp.tool(name="list_items")
def list_items() -> str:
    values = read_sheet(google_service, SPREADSHEET_ID, f"{SHEET_NAME}!A:B")
    if not values: return "데이터 없음"
    
    lines = []
    for row in values[1:]:
        if len(row) >= 2:
            lines.append(f"- {row[0]}: {row[1]}개")
    
    return "\n".join(lines) if lines else "품목 없음"

@mcp.tool(name="get_user_sheet_id")
def get_user_sheet_id(user_id: str) -> str:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT sheet_id FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "사용자를 찾을 수 없음"

if __name__ == "__main__":
    mcp.run(transport="streamable-http")