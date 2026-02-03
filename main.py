# ============================================
# 슬기로운 기업경영 - Backend v2.0
# Bizinfo + K-Startup + Claude API 연동
# ============================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx
import xml.etree.ElementTree as ET
import anthropic
import os
import json
import asyncio

app = FastAPI(title="N2B Backend v2.0", description="기업마당 + K-Startup + Claude 연동")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# API 키 (환경변수에서 읽기)
# ============================================
BIZINFO_API_KEY = os.getenv("BIZINFO_API_KEY", "f41G7V")
KSTARTUP_API_KEY = os.getenv("KSTARTUP_API_KEY", "47bd938c975a8989c5561a813fe66fcd68b76bfc4b4d54ca33345923b5b51897")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")  # Render 환경변수에 설정

# ============================================
# 요청 모델
# ============================================
class AnalyzeRequest(BaseModel):
    worry: str
    region: str = "전체"

class MatchRequest(BaseModel):
    n2b_not: str
    n2b_but: str
    n2b_because: str
    keywords: list[str]
    region: str = "전체"

# ============================================
# 기업마당 API - 실제 공고 조회
# ============================================
async def fetch_bizinfo_programs(keyword: Optional[str] = None, count: int = 100) -> list:
    url = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
    params = {
        "crtfcKey": BIZINFO_API_KEY,
        "dataType": "xml",
        "searchCnt": count,
    }
    if keyword:
        params["searchKind"] = keyword

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            programs = []

            for item in root.findall(".//item"):
                pblanc_id = item.findtext("pblancId", "")
                program = {
                    "id": pblanc_id,
                    "name": item.findtext("pblancNm", ""),
                    "agency": item.findtext("jrsdInsttNm", ""),
                    "target": item.findtext("trgetNm", ""),
                    "period": item.findtext("reqstBeginEndDe", ""),
                    "support_content": item.findtext("sprtCn", ""),
                    "url": f"https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId={pblanc_id}" if pblanc_id else "https://www.bizinfo.go.kr",
                    "source": "기업마당"
                }
                programs.append(program)

            return programs
    except Exception as e:
        print(f"[기업마당 오류] {e}")
        return []

# ============================================
# K-Startup API - 창업지원사업 조회
# ============================================
async def fetch_kstartup_programs(keyword: Optional[str] = None, per_page: int = 100) -> list:
    url = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
    params = {
        "ServiceKey": KSTARTUP_API_KEY,
        "page": 1,
        "perPage": per_page,
        "returnType": "json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            items = data.get("data", [])
            programs = []

            for item in items:
                program = {
                    "id": item.get("PBLANC_ID", ""),
                    "name": item.get("PBLANC_NM", ""),
                    "agency": item.get("DEPARTMENT_NM", ""),
                    "target": item.get("TRGET_NM", ""),
                    "period": f"{item.get('RCPT_BGNG_DT', '')} ~ {item.get('RCPT_END_DT', '')}",
                    "support_content": item.get("SPRT_CN", ""),
                    "url": item.get("DETAIL_PAGE_URL", "https://www.k-startup.go.kr"),
                    "source": "K-Startup"
                }
                programs.append(program)

            return programs
    except Exception as e:
        print(f"[K-Startup 오류] {e}")
        return []

# ============================================
# Claude로 N2B 분석
# ============================================
async def analyze_with_claude(worry: str) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""기업 대표의 고민: {worry}

이 고민을 N2B(NOT-BUT-BECAUSE) 프레임워크로 분석하고, 정부지원사업 검색 키워드를 추출해주세요.

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "not": "핵심 문제가 ~이 아니라",
  "but": "진짜 문제는 ~이다",
  "because": "왜냐하면 ~때문이다",
  "keywords": ["키워드1", "키워드2", "키워드3"]
}}"""
        }]
    )

    text = response.content[0].text
    json_match = __import__('re').search(r'\{[\s\S]*\}', text)
    if json_match:
        return json.loads(json_match.group())
    return {"not": "분석 실패", "but": "", "because": "", "keywords": []}

# ============================================
# Claude로 매칭 점수 계산
# ============================================
async def score_programs_with_claude(n2b: dict, programs: list, region: str) -> list:
    if not programs:
        return []
    
    # 상위 30개만 Claude에게 매칭 요청 (비용 절감)
    candidates = programs[:30]
    program_list = "\n".join([
        f"{i+1}. [{p['source']}] {p['name']} | {p['agency']} | {p['period']}"
        for i, p in enumerate(candidates)
    ])

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""N2B 분석 결과를 바탕으로 아래 실제 정부지원사업 중 가장 적합한 5개를 선택하고 매칭 점수를 매겨주세요.

N2B 분석:
- NOT: {n2b.get('not', '')}
- BUT: {n2b.get('but', '')}
- BECAUSE: {n2b.get('because', '')}
- 키워드: {', '.join(n2b.get('keywords', []))}
- 지역: {region}

실제 공고 목록:
{program_list}

반드시 아래 JSON 배열 형식으로만 답변하세요. 번호는 위 목록의 번호입니다:
[
  {{"index": 1, "fit_score": 92, "reason": "추천 이유"}},
  {{"index": 3, "fit_score": 87, "reason": "추천 이유"}}
]"""
        }]
    )

    text = response.content[0].text
    json_match = __import__('re').search(r'\[[\s\S]*\]', text)
    
    results = []
    if json_match:
        try:
            scored = json.loads(json_match.group())
            for item in scored:
                idx = item.get("index", 1) - 1
                if 0 <= idx < len(candidates):
                    prog = candidates[idx].copy()
                    prog["fit_score"] = item.get("fit_score", 80)
                    prog["reason"] = item.get("reason", "")
                    results.append(prog)
        except:
            pass

    return results

# ============================================
# API 엔드포인트
# ============================================

@app.get("/")
async def root():
    return {"status": "ok", "version": "2.0", "message": "N2B Backend - Bizinfo + K-Startup 연동"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

# 1) N2B 분석
@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
        result = await analyze_with_claude(req.worry)
        return {"success": True, "n2b": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2) 실제 공고 매칭
@app.post("/api/match")
async def match(req: MatchRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
        # 기업마당 + K-Startup 동시 조회
        keyword = req.keywords[0] if req.keywords else None
        bizinfo_task = fetch_bizinfo_programs(keyword)
        kstartup_task = fetch_kstartup_programs(keyword)
        
        bizinfo_programs, kstartup_programs = await asyncio.gather(
            bizinfo_task, kstartup_task
        )
        
        all_programs = bizinfo_programs + kstartup_programs
        
        n2b = {
            "not": req.n2b_not,
            "but": req.n2b_but,
            "because": req.n2b_because,
            "keywords": req.keywords
        }
        
        # Claude로 매칭 점수 계산
        matched = await score_programs_with_claude(n2b, all_programs, req.region)
        
        return {
            "success": True,
            "total_fetched": len(all_programs),
            "bizinfo_count": len(bizinfo_programs),
            "kstartup_count": len(kstartup_programs),
            "matched": matched
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3) 공고 목록 직접 조회 (디버그용)
@app.get("/api/programs")
async def get_programs(keyword: Optional[str] = None):
    bizinfo = await fetch_bizinfo_programs(keyword)
    kstartup = await fetch_kstartup_programs(keyword)
    return {
        "bizinfo_count": len(bizinfo),
        "kstartup_count": len(kstartup),
        "total": len(bizinfo) + len(kstartup),
        "programs": bizinfo + kstartup
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
