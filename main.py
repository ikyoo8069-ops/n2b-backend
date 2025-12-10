from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import json
import csv
import io
import urllib.request
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# CSV 파일에서 정책 데이터 로드
# ============================================
POLICIES = []

# GitHub Raw URL
CSV_URL = "https://raw.githubusercontent.com/ikyoo8069-ops/n2b-backend/main/policies.csv"

def load_policies():
    """GitHub에서 CSV 다운로드하여 로드"""
    global POLICIES
    try:
        with urllib.request.urlopen(CSV_URL, timeout=60) as response:
            content = response.read().decode('euc-kr')
            reader = csv.DictReader(io.StringIO(content))
            POLICIES = []
            for row in reader:
                POLICIES.append({
                    "id": row.get("번호", ""),
                    "category": row.get("분야", ""),
                    "title": row.get("사업명", ""),
                    "start_date": row.get("신청시작일", ""),
                    "end_date": row.get("신청종료일", ""),
                    "agency": row.get("소관기관", ""),
                    "executor": row.get("수행기관", ""),
                    "reg_date": row.get("등록일자", ""),
                    "url": row.get("상세URL", "")
                })
            print(f"✅ {len(POLICIES)}개 정책 데이터 로드 완료!")
    except Exception as e:
        print(f"❌ CSV 로드 실패: {e}")

# 서버 시작 시 데이터 로드
load_policies()

# ============================================
# 요청/응답 모델
# ============================================
class AnalyzeRequest(BaseModel):
    apiKey: str
    proposalText: str

class MatchRequest(BaseModel):
    apiKey: str
    n2bAnalysis: dict

class SearchRequest(BaseModel):
    keyword: str

# ============================================
# 정책 검색 함수
# ============================================
def search_policies(keywords: list, limit: int = 20) -> list:
    """키워드로 정책 검색"""
    results = []
    
    for policy in POLICIES:
        score = 0
        title = policy.get("title", "").lower()
        cat = policy.get("category", "").lower()
        agency = policy.get("agency", "").lower()
        
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in title:
                score += 3
            if kw_lower in cat:
                score += 2
            if kw_lower in agency:
                score += 1
        
        if score > 0:
            results.append({**policy, "match_score": score})
    
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results[:limit]

# ============================================
# API 엔드포인트
# ============================================
@app.get("/")
async def root():
    return {
        "message": "N2B API Server v3.0",
        "total_policies": len(POLICIES)
    }

@app.get("/stats")
async def stats():
    categories = {}
    for p in POLICIES:
        cat = p.get("category", "기타")
        if cat:
            categories[cat] = categories.get(cat, 0) + 1
    return {"total": len(POLICIES), "categories": categories}

@app.get("/reload")
async def reload():
    load_policies()
    return {"total": len(POLICIES)}

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    try:
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""다음 사업계획서를 N2B 프레임워크로 분석해주세요.

사업계획서:
{request.proposalText}

JSON으로만 답변:
{{"N": "문제점", "B": "솔루션", "C": "근거", "keywords": ["키워드1", "키워드2", "키워드3"], "category": "분야"}}
"""
            }]
        )
        
        text = message.content[0].text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/match")
async def match(request: MatchRequest):
    try:
        if len(POLICIES) == 0:
            load_policies()
        
        n2b = request.n2bAnalysis
        keywords = n2b.get("keywords", [])
        
        candidates = search_policies(keywords, limit=30)
        if not candidates:
            candidates = POLICIES[:30]
        
        client = anthropic.Anthropic(api_key=request.apiKey)
        candidates_text = json.dumps(candidates[:15], ensure_ascii=False, indent=2)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": f"""N2B 분석과 정부지원사업 매칭:

N2B:
- N: {n2b['N']}
- B: {n2b['B']}
- C: {n2b['C']}
- 키워드: {', '.join(keywords)}

후보 ({len(POLICIES)}개 중):
{candidates_text}

JSON으로 3개 선정:
{{"matches": [{{"title": "", "category": "", "agency": "", "deadline": "", "url": "", "score": 9, "reason": ""}}]}}
"""
            }]
        )
        
        text = message.content[0].text.replace("```json", "").replace("```", "").strip()
        start = text.find('{')
        end = text.rfind('}') + 1
        result = json.loads(text[start:end]) if start != -1 else {"matches": []}
        result["total_searched"] = len(POLICIES)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search")
async def search(request: SearchRequest):
    if len(POLICIES) == 0:
        load_policies()
    results = search_policies([request.keyword], limit=20)
    return {"keyword": request.keyword, "total": len(POLICIES), "found": len(results), "results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
