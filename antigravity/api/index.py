from flask import Flask, jsonify, render_template, request
import urllib.request
import json
import os

# ==========================================
# [TMAP API 설정] 발급받은 TMAP AppKey가 있다면 아래 입력하세요.
# 없거나 빈 문자열("")일 경우, 정밀 OSRM 도로망 매칭 엔진으로 자동 대체됩니다.
# ==========================================
TMAP_APP_KEY = ""


# Vercel serverless functions are located in the api/ directory.
# We set template_folder pointing to the root-level templates directory.
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../templates'))

# 임시 주차장 데이터 (창원대학교 중심)
# - 난이도: "하" (초록색 마커 추천 - 넓고 쾌적)
# - 난이도: "상" (빨간색 마커 경고 - 좁고 복잡)
mock_parking_lots = [
    {
        "id": 1,
        "name": "창원대 정문 노외주차장",
        "lat": 35.244200,
        "lng": 128.689500,
        "difficulty": "하",
        "difficulty_desc": "난이도 하 (초보 추천)",
        "congestion": "여유",
        "capacity_total": 100,
        "capacity_available": 35,
        "price_per_hour": 1500,
        "description": "구획선이 넓고 주차가 매우 직관적입니다. 진출입로가 시원하게 뚫려있어 회전 구간이 없습니다.",
        "tags": ["넓은 공간", "평지 주차", "초보 필수코스"]
    },
    {
        "id": 2,
        "name": "사림동 제일 공영주차장",
        "lat": 35.241500,
        "lng": 128.695000,
        "difficulty": "하",
        "difficulty_desc": "난이도 하 (초보 추천)",
        "congestion": "여유",
        "capacity_total": 50,
        "capacity_available": 12,
        "price_per_hour": 1000,
        "description": "지상 단층 주차장으로 기둥 충돌 위험이 전혀 없으며, 전면 주차가 편리하도록 앞뒤 간격이 넓습니다.",
        "tags": ["기둥 없음", "단층 평면", "시야 확보 용이"]
    },
    {
        "id": 3,
        "name": "창원대 대학본부 지하주차장",
        "lat": 35.247000,
        "lng": 128.693500,
        "difficulty": "상",
        "difficulty_desc": "난이도 상 (좁고 위험)",
        "congestion": "혼잡",
        "capacity_total": 80,
        "capacity_available": 5,
        "price_per_hour": 2000,
        "description": "지하로 내려가는 램프 구간이 매우 좁고 급경사입니다. 내부 기둥 간격이 좁아 문콕과 긁힘 주의가 필요합니다.",
        "tags": ["급경사 램프", "좁은 기둥", "회전각 불리"]
    },
    {
        "id": 4,
        "name": "사림동 원룸가 골목 노상주차장",
        "lat": 35.248200,
        "lng": 128.687500,
        "difficulty": "상",
        "difficulty_desc": "난이도 상 (좁고 위험)",
        "congestion": "혼잡",
        "capacity_total": 20,
        "capacity_available": 2,
        "price_per_hour": 500,
        "description": "평행 주차가 필수적인 좁은 골목입니다. 마주 오는 차량과 비켜 가기 곤란하며 시야 사각지대가 많습니다.",
        "tags": ["평행주차 필수", "좁은 골목", "교행 곤란"]
    }
]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/parking-lots')
def get_parking_lots():
    return jsonify(mock_parking_lots)

@app.route('/api/route')
def get_route():
    start_lng = request.args.get('start_lng')
    start_lat = request.args.get('start_lat')
    dest_lng = request.args.get('dest_lng')
    dest_lat = request.args.get('dest_lat')
    
    if not all([start_lng, start_lat, dest_lng, dest_lat]):
        return jsonify({"code": "InvalidParameters"}), 400

    # 1. Try TMAP Routes API first (if TMAP_APP_KEY is set)
    if TMAP_APP_KEY and TMAP_APP_KEY.strip():
        tmap_url = "https://apis.openapi.sk.com/tmap/routes?version=1"
        req_body = {
            "startX": float(start_lng),
            "startY": float(start_lat),
            "endX": float(dest_lng),
            "endY": float(dest_lat),
            "startName": "출발지",
            "endName": "목적지",
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO"
        }
        
        headers = {
            "appKey": TMAP_APP_KEY.strip(),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        try:
            req_data = json.dumps(req_body).encode('utf-8')
            req = urllib.request.Request(tmap_url, data=req_data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    features = data.get("features", [])
                    
                    if features:
                        # Extract total distance and time from first feature
                        first_props = features[0].get("properties", {})
                        distance = first_props.get("totalDistance", 0)
                        duration = first_props.get("totalTime", 0)
                        
                        points = []
                        instruction = "안내 경로를 따라 주행을 시작합니다."
                        direction_icon = "fa-solid fa-turn-up"
                        
                        found_instruction = False
                        for feat in features:
                            geom = feat.get("geometry", {})
                            props = feat.get("properties", {})
                            geom_type = geom.get("type")
                            
                            # Parse coordinates
                            if geom_type == "LineString":
                                coords = geom.get("coordinates", [])
                                for c in coords:
                                    points.append([c[1], c[0]]) # convert [lng, lat] to [lat, lng]
                                    
                            elif geom_type == "Point":
                                if not found_instruction:
                                    desc = props.get("description", "")
                                    turn = props.get("turnType", 0)
                                    if desc and "출발" not in desc and "경로" not in desc:
                                        instruction = desc
                                        found_instruction = True
                                        
                                        if turn == 12:
                                            direction_icon = "fa-solid fa-turn-left"
                                        elif turn == 13:
                                            direction_icon = "fa-solid fa-turn-right"
                                        elif turn == 14:
                                            direction_icon = "fa-solid fa-arrow-rotate-left"
                                        elif turn in [16, 17]:
                                            direction_icon = "fa-solid fa-turn-left"
                                        elif turn in [18, 19]:
                                            direction_icon = "fa-solid fa-turn-right"
                                            
                        if not found_instruction and features:
                            for feat in features:
                                desc = feat.get("properties", {}).get("description")
                                if desc:
                                    instruction = desc
                                    break
                                    
                        return jsonify({
                            "code": "Ok",
                            "source": "tmap",
                            "points": points,
                            "distance": distance,
                            "duration": duration,
                            "instruction": instruction,
                            "direction_icon": direction_icon
                        })
        except Exception as e:
            print("TMAP Directions API error, falling back to OSRM:", e)
 
    # 2. Fallback to OSRM Directions API (road-following coordinates)
    osrm_url = f"https://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{dest_lng},{dest_lat}?overview=full&geometries=geojson&steps=true"
    try:
        req = urllib.request.Request(osrm_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get("code") == "Ok" and "routes" in data and len(data["routes"]) > 0:
                route = data["routes"][0]
                distance = route.get("distance", 0)
                duration = route.get("duration", 0)
                
                coords = route.get("geometry", {}).get("coordinates", [])
                points = [[c[1], c[0]] for c in coords]
                
                instruction = "대로변 직진 후 교통 신호를 따라 진입"
                direction_icon = "fa-solid fa-turn-up"
                
                legs = route.get("legs", [])
                if legs:
                    steps = legs[0].get("steps", [])
                    first_real_step = None
                    for step in steps:
                        m = step.get("maneuver", {})
                        if m.get("type") != "depart" and step.get("name"):
                            first_real_step = step
                            break
                    
                    if first_real_step:
                        step_name = first_real_step.get("name", "")
                        modifier = first_real_step.get("maneuver", {}).get("modifier", "")
                        
                        turn_action = "직진"
                        if "left" in modifier:
                            turn_action = "좌회전"
                            direction_icon = "fa-solid fa-turn-left"
                        elif "right" in modifier:
                            turn_action = "우회전"
                            direction_icon = "fa-solid fa-turn-right"
                        elif "uturn" in modifier:
                            turn_action = "유턴"
                            direction_icon = "fa-solid fa-arrow-rotate-left"
                            
                        instruction = f"{step_name} 방면 {turn_action} 후 300m 앞 진입"
                    else:
                        hash_val = int(float(start_lat) * 10000)
                        fallback_directions = [
                            "창원대로 사거리 방면 좌회전 후 300m 앞 진입",
                            "사림로 교차로 방면 우회전 후 200m 앞 진입",
                            "대학본부 방면 직진 후 우회전하여 주차장 진입",
                            "경남도의회 삼거리 방면 우회전 후 서행 진입"
                        ]
                        instruction = fallback_directions[hash_val % len(fallback_directions)]
                        
                return jsonify({
                    "code": "Ok",
                    "source": "osrm",
                    "points": points,
                    "distance": distance,
                    "duration": duration,
                    "instruction": instruction,
                    "direction_icon": direction_icon
                })
    except Exception as e:
        print("OSRM Fallback API error:", e)
 
    # 3. Last resort fallback
    points = [
        [float(start_lat), float(start_lng)],
        [float(start_lat), float(dest_lng)],
        [float(dest_lat), float(dest_lng)]
    ]
    return jsonify({
        "code": "Ok",
        "source": "fallback",
        "points": points,
        "distance": 850,
        "duration": 240,
        "instruction": "창원대로 사거리 방면 좌회전 후 300m 앞 진입 (데모 안전 안내)",
        "direction_icon": "fa-solid fa-turn-left"
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
