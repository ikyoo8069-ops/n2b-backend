# ============================================
# 슬기로운 기업경영 - Backend v2.2
# Bizinfo + K-Startup + Claude API 연동
# + 제안서/PPT + 진흥원 N2B 분석
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
import re

app = FastAPI(title="N2B Backend v2.2", description="기업마당 + K-Startup + Claude 연동 + 제안서 + 진흥원")

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
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")

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

class ProposalRequest(BaseModel):
    company_info: str
    n2b_not: str
    n2b_but: str
    n2b_because: str
    program_name: str
    program_description: str
    program_budget: str

class PptRequest(BaseModel):
    company_info: str
    n2b_not: str
    n2b_but: str
    n2b_because: str
    program_name: str
    program_description: str
    program_budget: str

class AgencyAnalyzeRequest(BaseModel):
    worry: str

class AgencyDeepDiveRequest(BaseModel):
    previous_but: str
    messages: list = []

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
# Claude 호출 함수들
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
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        return json.loads(json_match.group())
    return {"not": "분석 실패", "but": "", "because": "", "keywords": []}


async def score_programs_with_claude(n2b: dict, programs: list, region: str) -> list:
    if not programs:
        return []
    
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
    json_match = re.search(r'\[[\s\S]*\]', text)
    
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


async def generate_proposal_with_claude(req: ProposalRequest) -> str:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""다음 정보를 바탕으로 정부지원사업 제안서 초안을 작성해주세요.

기업 정보:
{req.company_info}

N2B 분석 결과:
- NOT: {req.n2b_not}
- BUT: {req.n2b_but}
- BECAUSE: {req.n2b_because}

선택한 지원사업:
- 사업명: {req.program_name}
- 설명: {req.program_description}
- 지원 규모: {req.program_budget}

제안서는 다음 섹션으로 구성해주세요:
1. 사업 개요
2. 추진 배경 및 필요성 (N2B 분석 기반)
3. 사업 목표
4. 추진 전략 및 방법
5. 기대 효과

각 섹션을 구체적으로 작성해주세요."""
        }]
    )

    return response.content[0].text


async def generate_ppt_with_claude(req: PptRequest) -> str:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""다음 정보를 바탕으로 발표자료(PPT) 구성안을 작성해주세요.

기업 정보:
{req.company_info}

N2B 분석 결과:
- NOT: {req.n2b_not}
- BUT: {req.n2b_but}
- BECAUSE: {req.n2b_because}

선택한 지원사업:
- 사업명: {req.program_name}
- 설명: {req.program_description}
- 지원 규모: {req.program_budget}

발표자료는 10-15장 분량으로 구성해주세요.
각 슬라이드의 제목과 주요 내용을 상세히 작성해주세요."""
        }]
    )

    return response.content[0].text


# ============================================
# wise-agency용 Claude 함수들
# ============================================
AGENCY_SYSTEM_PROMPT = """당신은 '슬기로운 진흥원생활' 앱의 N2B 코치입니다.

성남산업진흥원 직원의 고민을 듣고 N2B(NOT-BUT-BECAUSE) 프레임워크로 분석해주세요.

## N2B 프레임워크
- NOT (N): 문제가 ~이 아니라 (표면적/잘못된 원인 부정)
- BUT (B): ~이다 (진짜 원인 제시)
- BECAUSE (C): 왜냐하면 ~때문이다 (근거/논리적 설명)

## 핵심 원리
1. N2B는 비교판단입니다. 모든 판단은 비교판단입니다.
2. 가설이 먼저입니다. 먼저 N2B(가설)를 세우고 → 실행으로 증명

## 능동지원 원칙
분석만 하지 말고, 구체적인 행동을 제안하세요.
제안 형식: "[목표]를 위해서는 [행동]을 해야 합니다"

그리고 다음 행동을 능동적으로 제시하세요. "~드릴까요?"가 아니라 "~드리겠습니다"로.

## 응답 형식 (반드시 JSON으로)
{
  "n2b": {
    "not": "~이 아니라",
    "but": "~이다", 
    "because": "~때문이다"
  },
  "suggestion": "[목표]를 위해서는 [행동]을 해야 합니다. 구체적 제안...",
  "nextAction": "~해드리겠습니다"
}"""


async def agency_analyze_with_claude(worry: str) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=AGENCY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": worry}]
    )

    text = response.content[0].text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        return json.loads(json_match.group())
    return {
        "n2b": {"not": "분석 중", "but": "문제의 본질을 파악하는 중입니다", "because": "조금 더 구체적인 상황을 알려주시면 정확한 분석이 가능합니다"},
        "suggestion": text
    }


async def agency_deepdive_with_claude(previous_but: str, messages: list) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    deep_prompt = f"""이전 분석에서 "{previous_but}"라고 했습니다.

이것이 왜 진짜 원인인지 더 깊이 분석해주세요.
이 원인의 더 근본적인 원인은 무엇인가요?

반드시 아래 JSON 형식으로만 답변해주세요:
{{
  "n2b": {{
    "not": "표면적 원인이 아니라",
    "but": "더 근본적인 원인이다", 
    "because": "왜냐하면 ~때문이다"
  }},
  "suggestion": "구체적 제안",
  "nextAction": "다음 행동을 ~해드리겠습니다"
}}"""

    api_messages = messages + [{"role": "user", "content": deep_prompt}]
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system="당신은 N2B 분석 전문가입니다. 반드시 지정된 JSON 형식으로만 답변하세요.",
        messages=api_messages
    )

    text = response.content[0].text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        return json.loads(json_match.group())
    return {
        "n2b": {"not": "분석 중", "but": "더 깊은 분석이 필요합니다", "because": "추가 정보가 필요합니다"},
        "suggestion": text
    }


# ============================================
# API 엔드포인트
# ============================================

@app.get("/")
async def root():
    return {"status": "ok", "version": "2.2", "message": "N2B Backend - Bizinfo + K-Startup + 제안서 + 진흥원"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

# 1) N2B 분석 (wise-biz + wise-proposal 공용)
@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
        result = await analyze_with_claude(req.worry)
        return {"success": True, "n2b": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2) 실제 공고 매칭 (wise-biz + wise-proposal 공용)
@app.post("/api/match")
async def match(req: MatchRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
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

# 3) 제안서 초안 생성 (wise-proposal 전용)
@app.post("/api/proposal")
async def proposal(req: ProposalRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
        text = await generate_proposal_with_claude(req)
        return {"success": True, "content": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4) PPT 구성안 생성 (wise-proposal 전용)
@app.post("/api/ppt-outline")
async def ppt_outline(req: PptRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
        text = await generate_ppt_with_claude(req)
        return {"success": True, "content": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5) 공고 목록 직접 조회 (디버그용)
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

# 6) 진흥원 N2B 분석 (wise-agency 전용)
@app.post("/api/agency-analyze")
async def agency_analyze(req: AgencyAnalyzeRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
        result = await agency_analyze_with_claude(req.worry)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7) 진흥원 깊이분석 (wise-agency 전용)
@app.post("/api/agency-deepdive")
async def agency_deepdive(req: AgencyDeepDiveRequest):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    
    try:
        result = await agency_deepdive_with_claude(req.previous_but, req.messages)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
