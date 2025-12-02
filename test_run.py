from mcp_server import (
    register_user_sheet,
    lookup_inventory,
    update_stock,
    check_threshold,
    forecast_depletion,
    list_items
)

ITEM_NAME = "A4_복사용지_80g"
MY_SHEET_ID = "1U6_t-ZDf6_qAemvSdp7_PQ7qMdLpgzxLHCiKiueVqEg"
USER_ID = "test_user_2"
CHANNEL = "console_test"

print(f"=== [설정] 테스트 품목: {ITEM_NAME} / 유저: {USER_ID} ===\n")

print("=== 1. 사용자 등록 및 시트 연결 (register_user_sheet) ===")
print(register_user_sheet(USER_ID, CHANNEL, MY_SHEET_ID))

print("\n" + "="*50 + "\n")

print("=== 2. 품목 전체 목록 조회 (list_items) ===")
print(list_items(USER_ID))

print("\n" + "="*50 + "\n")

print(f"=== 3. 재고 조회 테스트: {ITEM_NAME} (lookup_inventory) ===")
print(lookup_inventory(ITEM_NAME, USER_ID))

print("\n" + "="*50 + "\n")

print(f"=== 4. 재고 변경 테스트: {ITEM_NAME} -1개 차감 (update_stock) ===")
print(update_stock(ITEM_NAME, -1, USER_ID))

print("\n" + "="*50 + "\n")

print(f"=== 5. 변경 후 재고 확인 ({ITEM_NAME}) ===")
print(lookup_inventory(ITEM_NAME, USER_ID))

print("\n" + "="*50 + "\n")

print(f"=== 6. 임계치 체크 테스트 (100개 이하 알림) ===")
print(check_threshold(100, USER_ID))

print("\n" + "="*50 + "\n")

print(f"=== 7. 예측 툴 테스트 (forecast_depletion) ===")
print(forecast_depletion(ITEM_NAME, USER_ID))
