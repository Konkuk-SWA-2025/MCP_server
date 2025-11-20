from mcp_server import (
    lookup_inventory, 
    update_stock, 
    check_threshold, 
    forecast_depletion,
    register_user_sheet,
    get_user_sheet_id,
    list_items
)

ITEM_NAME = "A4_복사용지_80g"
MY_SHEET_ID = "1U6_t-ZDf6_qAemvSdp7_PQ7qMdLpgzxLHCiKiueVqEg"
USER_ID = "test_user_2"

print(f"=== [설정] 테스트 품목: {ITEM_NAME} / 시트 ID: {MY_SHEET_ID} ===\n")

print("=== 1. 사용자 등록 테스트 (SQLite) ===")
print(register_user_sheet(USER_ID, "discord", MY_SHEET_ID))

print("\n=== 2. 사용자 시트 조회 테스트 (SQLite) ===")
print(get_user_sheet_id(USER_ID))

print("\n=== 3. 품목 전체 목록 조회 (Google Sheet) ===")
print(list_items())

print(f"\n=== 4. 재고 조회 테스트: {ITEM_NAME} (Google Sheet) ===")
print(lookup_inventory(ITEM_NAME))

print(f"\n=== 5. 재고 변경 테스트: {ITEM_NAME} -1개 차감 (Google Sheet) ===")
print(update_stock(ITEM_NAME, -1))

print(f"\n=== 6. 임계치 체크 테스트 (Google Sheet) ===")
print(check_threshold(100))

print(f"\n=== 7. 예측 툴 테스트 (Google Sheet) ===")
print(forecast_depletion(ITEM_NAME))