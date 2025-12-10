from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import json
import csv
import os
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

def load_policies():
    global POLICIES
    csv_path = os.path.join(os.path.dirname(__file__), "중소벤처기업부_중소기업지원사업목록_20250331.csv")
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
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
def search_policies(keywords: list, category: str = None, limit: int = 20) -> list:
    """키워드로 정책 검색"""
    results = []
    
    for policy in POLICIES:
        score = 0
        title = policy.get("title", "").lower()
        cat = policy.get("category", "").lower()
        agency = policy.get("agency", "").lower()
        
        # 키워드 매칭 점수 계산
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in title:
                score += 3
            if kw_lower in cat:
                score += 2
            if kw_lower in agency:
                score += 1
        
        # 카테고리 필터
        if category and category.lower() not in cat:
            continue
        
        if score > 0:
            results.append({
                **policy,
                "match_score": score
            })
    
    # 점수순 정렬
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results[:limit]

# ============================================
# API 엔드포인트
# ============================================
@app.get("/")
async def root():
    return {
        "message": "N2B API Server v3.0",
        "version": "3.0.0 - 전체 정책 DB 내장",
        "total_policies": len(POLICIES),
        "features": [
            f"bizinfo {len(POLICIES)}개 정책 내장",
            "N2B 분석",
            "AI 기반 매칭",
            "전체 데이터 검색"
        ]
    }

@app.get("/stats")
async def stats():
    """통계 정보"""
    categories = {}
    for p in POLICIES:
        cat = p.get("category", "기타")
        categories[cat] = categories.get(cat, 0) + 1
    
    return {
        "total": len(POLICIES),
        "categories": categories
    }

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """사업계획서 N2B 분석"""
    try:
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""다음 사업계획서를 N2B(NOT-BUT-BECAUSE) 프레임워크로 분석해주세요.

사업계획서:
{request.proposalText}

다음 형식의 JSON으로만 답변해주세요:
{{
    "N": "현재의 문제점 (2-3문장)",
    "B": "제안하는 솔루션 (2-3문장)",
    "C": "근거 및 기대효과 (2-3문장)",
    "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
    "category": "분야 (기술/창업/경영/금융/인력/수출/내수 중 하나)",
    "stage": "창업단계 (예비창업/초기창업/성장기)"
}}

keywords는 정부지원사업 검색에 사용할 핵심 키워드입니다.
"""
            }]
        )
        
        text = message.content[0].text
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/match")
async def match(request: MatchRequest):
    """N2B 분석 결과 기반 정부지원사업 매칭"""
    try:
        n2b = request.n2bAnalysis
        keywords = n2b.get("keywords", [])
        category = n2b.get("category", "")
        
        # 내장 DB에서 검색
        candidates = search_policies(keywords, limit=30)
        
        if not candidates:
            # 키워드 없이 카테고리로만 검색
            candidates = [p for p in POLICIES if category.lower() in p.get("category", "").lower()][:30]
        
        if not candidates:
            candidates = POLICIES[:30]
        
        # Claude로 최적 매칭 선정
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        candidates_text = json.dumps(candidates[:15], ensure_ascii=False, indent=2)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": f"""다음 N2B 분석 결과와 검색된 정부지원사업 목록을 비교하여 
가장 적합한 3개를 선정해주세요.

N2B 분석:
- N (문제점): {n2b['N']}
- B (솔루션): {n2b['B']}  
- C (근거): {n2b['C']}
- 키워드: {', '.join(keywords)}
- 분야: {category}

검색된 지원사업 목록 (총 {len(POLICIES)}개 중 상위 후보):
{candidates_text}

다음 JSON 형식으로만 답변해주세요:
{{
    "matches": [
        {{
            "title": "사업명",
            "category": "분야",
            "agency": "소관기관",
            "deadline": "신청종료일",
            "url": "상세URL",
            "score": 9,
            "reason": "이 사업이 적합한 이유 (N2B 관점에서 2-3문장)"
        }}
    ]
}}

가장 적합한 3개만 선정하고, score는 1-10점으로 매겨주세요.
reason은 N2B 분석 결과와 연결하여 왜 이 사업이 적합한지 설명해주세요.
"""
            }]
        )
        
        result_text = message.content[0].text
        result_text = result_text.replace("```json", "").replace("```", "").strip()
        
        start_idx = result_text.find('{')
        end_idx = result_text.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            result = json.loads(result_text[start_idx:end_idx])
        else:
            result = {"matches": []}
        
        # 검색된 총 개수 추가
        result["total_searched"] = len(POLICIES)
        result["candidates_found"] = len(candidates)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search")
async def search_direct(request: SearchRequest):
    """키워드로 직접 검색"""
    results = search_policies([request.keyword], limit=20)
    return {
        "keyword": request.keyword,
        "total_db": len(POLICIES),
        "found": len(results),
        "results": results
    }

@app.get("/categories")
async def get_categories():
    """분야별 통계"""
    categories = {}
    for p in POLICIES:
        cat = p.get("category", "기타")
        categories[cat] = categories.get(cat, 0) + 1
    return categories

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
