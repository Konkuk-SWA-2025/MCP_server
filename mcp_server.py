import os
import sqlite3
import datetime
import logging
import time
import random
import functools
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd
from prophet import Prophet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("InventorySystem")

KEY_FILE_PATH = 'bold-tooling-466206-a9-960a00bb4c78.json'
SHEET_NAME = 'Sheet1'
DB_FILE = "inventory_system.db"

def retry_with_backoff(retries=3, initial_delay=1, backoff_factor=2):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    if e.resp.status in [429, 500, 502, 503, 504]:
                        if i == retries - 1:
                            logger.error(f"API Retry 횟수 초과: {e}")
                            raise
                        sleep_time = delay + random.uniform(0, 0.5)
                        logger.warning(f"API 오류({e.resp.status}). {sleep_time:.2f}초 후 재시도 ({i+1}/{retries})")
                        time.sleep(sleep_time)
                        delay *= backoff_factor
                    else:
                        raise e
                except Exception as e:
                    logger.error(f"알 수 없는 오류: {e}")
                    raise e
        return wrapper
    return decorator

def authenticate_service_account(json_keyfile_path):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = service_account.Credentials.from_service_account_file(
        json_keyfile_path, scopes=SCOPES)
    return creds

def create_sheets_service(creds):
    return build('sheets', 'v4', credentials=creds)

@retry_with_backoff()
def read_sheet(service, spreadsheet_id, range_name):
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        values = result.get('values', [])
        return values
    except HttpError as err:
        logger.error(f'Read Error: {err}')
        return None

@retry_with_backoff()
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
        logger.error(f'Write Error: {err}')
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

def get_sheet_id_by_user(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT sheet_id FROM users WHERE user_id=? ORDER BY updated_at DESC LIMIT 1", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

@mcp.tool(name="register_user_sheet")
def register_user_sheet(user_id: str, channel: str, sheet_id: str) -> str:
    """사용자의 Google Sheet ID를 등록합니다."""
    if not google_service: return "구글 서비스 연결 실패"

    try:
        test_values = read_sheet(google_service, sheet_id, f"{SHEET_NAME}!A1:A1")
        if test_values is None:
            return "검증 실패: 시트를 읽을 수 없습니다. 시트 ID가 정확한지, 봇 계정에 편집 권한이 있는지 확인해주세요."
    except Exception as e:
        return f"검증 오류: 접근 테스트 중 에러가 발생했습니다. ({str(e)})"

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO users (user_id, channel, sheet_id, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, channel) DO UPDATE SET
            sheet_id=excluded.sheet_id,
            updated_at=CURRENT_TIMESTAMP
        ''', (user_id, channel, sheet_id))
        
        conn.commit()
        conn.close()
        return f"성공: {user_id}님의 시트({sheet_id})가 검증 및 등록되었습니다."
        
    except Exception as e:
        return f"실패: DB 저장 중 오류 ({e})"

@mcp.tool(name="lookup_inventory")
def lookup_inventory(item_name: str, user_id: str) -> str:
    """특정 품목의 재고를 조회합니다."""
    if not google_service: return "구글 서비스 연결 실패"
    
    sheet_id = get_sheet_id_by_user(user_id)
    if not sheet_id: return "오류: 등록된 시트가 없습니다. 먼저 시트를 등록해주세요."

    values = read_sheet(google_service, sheet_id, f"{SHEET_NAME}!A:C")
    if not values: return "시트 데이터를 읽을 수 없습니다."

    for row in values:
        if len(row) > 0 and row[0] == item_name:
            qty = row[1] if len(row) > 1 else "0"
            return f"성공: {item_name} 수량은 {qty}개 입니다."
            
    return f"실패: 품목 '{item_name}'이(가) 시트에 존재하지 않습니다."

@mcp.tool(name="update_stock")
def update_stock(item_name: str, quantity: int, user_id: str) -> str:
    """재고 수량을 변경합니다."""
    if not google_service: return "구글 서비스 연결 실패"

    sheet_id = get_sheet_id_by_user(user_id)
    if not sheet_id: return "오류: 등록된 시트가 없습니다."

    values = read_sheet(google_service, sheet_id, f"{SHEET_NAME}!A:B")
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
    result = write_sheet(google_service, sheet_id, range_name, [[new_qty]])
    
    if result:
        save_log(item_name, quantity, user_id, sheet_id, new_qty)
        return f"성공: '{item_name}' 재고 변경 완료 ({current_qty} -> {new_qty})"
    else:
        return "실패: 시트 업데이트 중 오류 발생"

@mcp.tool(name="check_threshold")
def check_threshold(check_quantity: int, user_id: str) -> str:
    """기준치 이하의 재고 품목을 확인합니다."""
    if not google_service: return "구글 서비스 연결 실패"

    sheet_id = get_sheet_id_by_user(user_id)
    if not sheet_id: return "오류: 등록된 시트가 없습니다."

    values = read_sheet(google_service, sheet_id, f"{SHEET_NAME}!A:B")
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
def forecast_depletion(item_name: str, user_id: str) -> str:
    """Prophet을 사용하여 품목 소진 시점을 예측합니다."""
    sheet_id = get_sheet_id_by_user(user_id)
    if not sheet_id: return "오류: 등록된 시트가 없습니다."

    try:
        conn = sqlite3.connect(DB_FILE)
        query = """
            SELECT created_at as ds, snapshot_qty as y 
            FROM logs 
            WHERE item_name = ? AND sheet_id = ? AND snapshot_qty IS NOT NULL 
            ORDER BY created_at ASC
        """
        df = pd.read_sql_query(query, conn, params=(item_name, sheet_id))
        conn.close()
    except Exception as e:
        return f"실패: DB 조회 중 오류 ({str(e)})"

    if df.empty:
        return "실패: 예측을 위한 과거 데이터(로그)가 없습니다."
    
    if len(df) < 30:
        return f"실패: 데이터가 너무 적습니다 (현재 {len(df)}개). 최소 30개 이상의 로그가 필요합니다."

    try:
        df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
        df['y'] = pd.to_numeric(df['y'])
    except Exception as e:
        return f"실패: 데이터 전처리 오류 ({str(e)})"

    current_qty = df.iloc[-1]['y']
    if current_qty <= 0:
        return "이미 재고가 소진되었습니다."

    try:
        logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
        
        m = Prophet(daily_seasonality=True)
        m.fit(df)

        future = m.make_future_dataframe(periods=60) 
        forecast = m.predict(future)

        current_date = pd.Timestamp.now()
        future_forecast = forecast[forecast['ds'] > current_date]
        
        depletion_rows = future_forecast[future_forecast['yhat'] <= 0]
        
        if not depletion_rows.empty:
            depletion_date = depletion_rows.iloc[0]['ds'].date()
            return f"성공(Prophet): '{item_name}'은 {depletion_date}경 소진될 것으로 예측됩니다."
        else:
            min_val = round(future_forecast['yhat'].min(), 1)
            return f"성공(Prophet): 향후 60일 내에는 소진되지 않을 것으로 보입니다. (최저 예상: {min_val}개)"

    except Exception as e:
        return f"실패: 모델 학습/예측 중 오류 발생 ({str(e)})"

def save_log(item_name: str, delta_qty: int, user_id: str, sheet_id: str, snapshot_qty: int = None):
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO logs (sheet_id, user_id, item_name, delta_qty, snapshot_qty)
            VALUES (?, ?, ?, ?, ?)
        ''', (sheet_id, user_id, item_name, delta_qty, snapshot_qty))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Log Save Error: {e}")

@mcp.tool(name="list_items")
def list_items(user_id: str) -> str:
    """전체 품목 리스트를 조회합니다."""
    if not google_service: return "구글 서비스 연결 실패"
    
    sheet_id = get_sheet_id_by_user(user_id)
    if not sheet_id: return "오류: 등록된 시트가 없습니다."

    values = read_sheet(google_service, sheet_id, f"{SHEET_NAME}!A:B")
    if not values: return "데이터 없음"
    
    lines = []
    for row in values[1:]:
        if len(row) >= 2:
            lines.append(f"- {row[0]}: {row[1]}개")
    
    return "\n".join(lines) if lines else "품목 없음"

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
