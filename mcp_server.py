import os
import gspread
import numpy as np
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from google.oauth2.service_account import Credentials
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
import logging

# 중앙 DB 모델 및 세션 임포트
from database_models import SessionLocal, StockLog

# --- 설정 로드 ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCP_Server")

GOOGLE_CREDENTIALS_JSON_PATH = os.getenv("GOOGLE_CREDENTIALS_JSON_PATH")
DEFAULT_SHEET_ID = os.getenv("DEFAULT_SHEET_ID", "")

mcp = FastMCP("ToolingServices")

# --- Google Sheets 서비스 (이전과 동일) ---
class GoogleSheetService:
    def __init__(self):
        self.client = None
        if GOOGLE_CREDENTIALS_JSON_PATH and os.path.exists(GOOGLE_CREDENTIALS_JSON_PATH):
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_JSON_PATH, scopes=scopes)
            self.client = gspread.authorize(creds)
        else:
            logger.warning("Google Credentials file not found. (MCP_Server)")

    def get_worksheet(self, sheet_id: str):
        if not self.client: return None
        try:
            if "spreadsheets/d/" in sheet_id:
                sheet_id = sheet_id.split("spreadsheets/d/")[1].split("/")[0]
            return self.client.open_by_key(sheet_id).get_worksheet(0)
        except Exception as e:
            logger.error(f"Sheet Access Error: {e}")
            return None

    def find_item_cell(self, worksheet, item_name: str):
        try:
            return worksheet.find(item_name, in_column=1) # A열 검색
        except gspread.exceptions.CellNotFound:
            return None

gs_service = GoogleSheetService()

# --- 다이어그램: '툴 정의' (MCP 도구들) ---

@mcp.tool()
def 재고_조회툴(item_name: str, sheet_id: str) -> str:
    """(재고-조회툴) 특정 품목의 현재 재고 수량을 조회합니다."""
    if not sheet_id: return "Error: Sheet ID is required."
    ws = gs_service.get_worksheet(sheet_id)
    if not ws: return "Error: Cannot access Google Sheet."
    cell = gs_service.find_item_cell(ws, item_name)
    if not cell: return f"Item '{item_name}' not found in sheet."
    try:
        qty = ws.cell(cell.row, 2).value
        return f"Item: {item_name}, Current Quantity: {qty}"
    except Exception as e:
        return f"Error reading quantity: {str(e)}"

@mcp.tool()
def 입출고_기록툴(item_name: str, delta: int, sheet_id: str) -> str:
    """(입출고-기록툴) 재고를 늘리거나 줄입니다 (delta: +5, -3 등). DB에 로그를 남기고 Google Sheet를 업데이트합니다."""
    if not sheet_id: return "Error: Sheet ID is required."
    ws = gs_service.get_worksheet(sheet_id)
    if not ws: return "Error: Cannot access Google Sheet."
    cell = gs_service.find_item_cell(ws, item_name)
    if not cell: return f"Item '{item_name}' not found."
    try:
        qty_cell_addr = f"B{cell.row}"
        current_qty = float(ws.acell(qty_cell_addr).value or 0)
        new_qty = current_qty + delta
        if new_qty < 0:
            return f"Error: Insufficient stock. Current: {current_qty}, Requested change: {delta}"
        
        ws.update_acell(qty_cell_addr, new_qty)
        
        db = SessionLocal()
        try:
            log = StockLog(item_name=item_name, quantity_change=delta, sheet_id=sheet_id)
            db.add(log)
            db.commit()
        finally:
            db.close()
            
        return f"Success. Adjusted {item_name} by {delta}. New Qty: {new_qty}."
    except Exception as e:
        return f"Error updating stock: {str(e)}"

@mcp.tool()
def 예측툴(item_name: str, sheet_id: str) -> str:
    """(예측툴) DB의 출고 로그를 기반으로 품목 소진일을 예측합니다."""
    db = SessionLocal()
    try:
        logs = db.query(StockLog).filter(
            StockLog.item_name == item_name, 
            StockLog.quantity_change < 0
        ).order_by(StockLog.created_at.asc()).all()
    finally:
        db.close()
    
    if len(logs) < 2:
        return f"Not enough data to predict depletion for {item_name}."
    
    start_date = logs[0].created_at
    X, y = [], []
    cumulative_consumption = 0
    for log in logs:
        days = (log.created_at - start_date).total_seconds() / 86400
        cumulative_consumption += abs(log.quantity_change)
        X.append([days]); y.append(cumulative_consumption)
    
    try:
        model = LinearRegression().fit(X, y)
        daily_consumption = model.coef_[0]
        if daily_consumption <= 0: return "Consumption trend is unclear."
        
        ws = gs_service.get_worksheet(sheet_id)
        cell = gs_service.find_item_cell(ws, item_name)
        current_qty = float(ws.cell(cell.row, 2).value or 0)
        
        days_left = current_qty / daily_consumption
        predicted_date = datetime.now() + timedelta(days=days_left)
        return f"Forecast for {item_name}: Approx. {days_left:.1f} days left. Estimated depletion: {predicted_date.strftime('%Y-%m-%d')}."
    except Exception as e:
        return f"Prediction failed: {str(e)}"

@mcp.tool()
def 임계치_체크툴(threshold: int = 10, sheet_id: str = "") -> str:
    """(임계치 체크툴) 지정된 수량(threshold) 이하인 모든 품목을 찾아 반환합니다."""
    if not sheet_id: sheet_id = DEFAULT_SHEET_ID
    if not sheet_id: return "Error: Sheet ID is required."
        
    ws = gs_service.get_worksheet(sheet_id)
    if not ws: return "Error: Cannot access Google Sheet."
    try:
        data = ws.get("A2:B") 
        low_stock = [row[0] for row in data if len(row) > 1 and row[0] and float(row[1] or 0) <= threshold]
        if not low_stock: return "All items are above the threshold."
        return f"Warning! Items below threshold ({threshold}): " + ", ".join(low_stock)
    except Exception as e:
        return f"Error checking thresholds: {str(e)}"

if __name__ == "__main__":
    logger.info("Starting Tooling Service (MCP Server) on port 8000...")
    mcp.run(transport="streamable-http", port=8000)