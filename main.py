# 修改 get_precise_weather 函式中的一個小地方，增加 Debug 能力
def get_precise_weather():
    dist_configs = [
        {"id": "F-D0047-063", "name": "北投區"},
        {"id": "F-D0047-063", "name": "萬華區"},
        {"id": "F-D0047-063", "name": "信義區"},
        {"id": "F-D0047-071", "name": "淡水區"},
        {"id": "F-D0047-003", "name": "礁溪鄉"}
    ]
    
    weather_results = []
    
    for item in dist_configs:
        api_id = item["id"]
        dist_name = item["name"]
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&locationName={dist_name}&elementName=Wx,MinT,MaxT,PoP12h"
            r = requests.get(url, timeout=12)
            
            if r.status_code == 200:
                data = r.json()
                # 取得 records 底下的所有內容
                records = data.get('records', {})
                # 鄉鎮預報在有篩選 locationName 時，locations 可能是一個清單
                locations_node = records.get('locations', [{}])[0]
                loc_list = locations_node.get('location', [])
                
                if loc_list:
                    loc_data = loc_list[0]
                    elements = loc_data.get('weatherElement', [])
                    # 解析各個天氣數值
                    e = {elem['elementName']: elem['time'][0]['elementValue'][0]['value'] for elem in elements}
                    
                    wx = e.get('Wx', '未知')
                    mint = e.get('MinT', '--')
                    maxt = e.get('MaxT', '--')
                    pop = e.get('PoP12h', '0')
                    
                    weather_results.append(f"📍 {dist_name} {mint}~{maxt}° {wx} (降雨{pop}%)")
                else:
                    # 如果找不到，印出 records 結構以便觀察
                    print(f"⚠️ {dist_name} 找不到資料節點: {records.keys()}")
                    weather_results.append(f"📍 {dist_name} 暫無資料")
            else:
                weather_results.append(f"📍 {dist_name} 服務繁忙({r.status_code})")
        except Exception as err:
            print(f"❌ {dist_name} 錯誤: {err}")
            weather_results.append(f"📍 {dist_name} 讀取逾時")
            
    return "\n".join(weather_results)
