# ============================================
# 슬기로운 기업경영 - Backend v2.5
# Bizinfo + K-Startup + Claude API 연동
# + 제안서/PPT + 진흥원 + 일일사용제한
# + 조달청 입찰/낙찰/가격 API (wise-bid)
# + 입찰공고 N2B 매칭 기능
# ============================================

from fastapi import FastAPI, HTTPException, Request
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
from datetime import date, datetime

app = FastAPI(title="N2B Backend v2.5", description="기업마당 + K-Startup + Claude + 제안서 + 진흥원 + 조달청입찰 + 입찰매칭")

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
PUBLIC_DATA_API_KEY = os.getenv("PUBLIC_DATA_API_KEY", "47bd938c975a8989c5561a813fe66fcd68b76bfc4b4d54ca33345923b5b51897")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
PREMIUM_KEY = os.getenv("PREMIUM_KEY", "wise2025")

# ============================================
# 일일 사용 제한 시스템
# ============================================
LIMITS = {
    "biz": {"normal": 10, "premium": 200},
    "proposal": {"normal": 10, "premium": 200},
    "agency": {"normal": 100},
    "bid": {"normal": 10, "premium": 200}
}

daily_usage: dict = {}


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(ip: str, app_type: str, is_premium: bool = False) -> dict:
    today = str(date.today())
    
    if today not in daily_usage:
        daily_usage.clear()
        daily_usage[today] = {}
    
    if ip not in daily_usage[today]:
        daily_usage[today][ip] = {"biz": 0, "proposal": 0, "agency": 0, "bid": 0}
    
    usage = daily_usage[today][ip]
    current = usage.get(app_type, 0)
    
    if app_type in ("biz", "proposal", "bid"):
        limit = LIMITS[app_type]["premium"] if is_premium else LIMITS[app_type]["normal"]
    else:
        limit = LIMITS["agency"]["normal"]
    
    remaining = limit - current
    
    if remaining <= 0:
        tier = "프리미엄" if is_premium else "일반"
        raise HTTPException(
            status_code=429,
            detail=f"일일 사용 한도({limit}회)를 초과했습니다. ({tier})"
        )
    
    usage[app_type] = current + 1
    return {"used": current + 1, "limit": limit, "remaining": remaining - 1}

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

# 조달청 입찰 관련 모델
class BidSearchRequest(BaseModel):
    keyword: str
    bid_type: str = "물품"
    count: int = 20

class BidPriceAnalyzeRequest(BaseModel):
    bid_name: str
    estimated_price: int
    our_cost: int
    bid_type: str = "물품"
    n2b_not: str = ""
    n2b_but: str = ""
    n2b_because: str = ""

class BidDecisionRequest(BaseModel):
    bid_name: str
    estimated_price: int
    our_cost: int
    pros: str
    cons: str

# 입찰공고 매칭용 모델
class BidAnalyzeNeedsRequest(BaseModel):
    company_info: str  # 회사 역량, 관심분야
    preferred_type: str = "전체"  # 물품, 공사, 용역, 외자, 전체
    budget_range: str = ""  # 예: "1억~5억"

class BidMatchRequest(BaseModel):
    n2b_not: str
    n2b_but: str
    n2b_because: str
    keywords: list[str]
    preferred_type: str = "전체"

# ============================================
# 기업마당 API
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
# K-Startup API
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
# 조달청 API - 입찰공고 조회
# ============================================
async def fetch_bid_announcements(keyword: str, bid_type: str = "물품", count: int = 20) -> list:
    type_endpoints = {
        "물품": "getBidPblancListInfoThngPPSSrch",
        "공사": "getBidPblancListInfoCnstwkPPSSrch", 
        "용역": "getBidPblancListInfoServcPPSSrch",
        "외자": "getBidPblancListInfoFrgcptPPSSrch"
    }
    
    endpoint = type_endpoints.get(bid_type, "getBidPblancListInfoThngPPSSrch")
    # 올바른 End Point 사용
    url = f"https://apis.data.go.kr/1230000/ad/BidPublicInfoService/{endpoint}"
    
    # 검색 기간: 30일 전부터 오늘까지
    from datetime import timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    params = {
        "ServiceKey": PUBLIC_DATA_API_KEY,
        "pageNo": 1,
        "numOfRows": count,
        "type": "json",
        "inqryDiv": "1",  # 필수: 조회구분 (1=공고명)
        "inqryBgnDt": start_date.strftime("%Y%m%d") + "0000",
        "inqryEndDt": end_date.strftime("%Y%m%d") + "2359"
    }
    
    # 키워드가 있으면 추가
    if keyword and keyword.strip():
        params["bidNm"] = keyword

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("response", {}).get("body", {}).get("items", [])
            
            # items가 없거나 빈 경우
            if not items:
                return []
            
            # items가 딕셔너리인 경우 (단일 결과)
            if isinstance(items, dict):
                items = [items]
            
            # items가 리스트 안에 딕셔너리로 감싸져 있는 경우
            if isinstance(items, list) and len(items) > 0 and isinstance(items[0], dict) and "item" in items[0]:
                items = items[0].get("item", [])
                if isinstance(items, dict):
                    items = [items]
            
            bids = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                bid = {
                    "bid_no": item.get("bidNtceNo", ""),
                    "bid_name": item.get("bidNtceNm", ""),
                    "agency": item.get("ntceInsttNm", ""),
                    "demand_agency": item.get("dminsttNm", ""),
                    "estimated_price": item.get("presmptPrce", 0),
                    "base_price": item.get("asignBdgtAmt", 0),
                    "bid_method": item.get("bidMethdNm", ""),
                    "contract_method": item.get("cntrctCnclsMthdNm", ""),
                    "deadline": item.get("bidClseDt", ""),
                    "open_date": item.get("opengDt", ""),
                    "url": item.get("bidNtceDtlUrl", ""),
                    "bid_type": bid_type
                }
                bids.append(bid)
            return bids
    except Exception as e:
        print(f"[조달청 입찰공고 오류] {e}")
        return []

# ============================================
# 조달청 API - 낙찰정보 조회
# ============================================
async def fetch_winning_bids(keyword: str, bid_type: str = "물품", count: int = 20) -> list:
    type_endpoints = {
        "물품": "getOpengResultListInfoThngPPSSrch",
        "공사": "getOpengResultListInfoCnstwkPPSSrch",
        "용역": "getOpengResultListInfoServcPPSSrch",
        "외자": "getOpengResultListInfoFrgcptPPSSrch"
    }
    
    endpoint = type_endpoints.get(bid_type, "getOpengResultListInfoThngPPSSrch")
    url = f"https://apis.data.go.kr/1230000/ScsbidInfoService/{endpoint}"
    
    params = {
        "ServiceKey": PUBLIC_DATA_API_KEY,
        "pageNo": 1,
        "numOfRows": count,
        "type": "json",
        "bidNm": keyword,
        "inqryDiv": "1"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("response", {}).get("body", {}).get("items", [])
            if not items:
                return []
            results = []
            for item in items:
                estimated = float(item.get("presmptPrce", 0) or 0)
                winning = float(item.get("sucsfbidAmt", 0) or 0)
                rate = (winning / estimated * 100) if estimated > 0 else 0
                result = {
                    "bid_no": item.get("bidNtceNo", ""),
                    "bid_name": item.get("bidNtceNm", ""),
                    "agency": item.get("ntceInsttNm", ""),
                    "estimated_price": estimated,
                    "winning_price": winning,
                    "winning_rate": round(rate, 2),
                    "winner": item.get("sucsfbidCorpNm", ""),
                    "open_date": item.get("opengDt", ""),
                    "participant_count": item.get("prtcptCnum", 0)
                }
                results.append(result)
            return results
    except Exception as e:
        print(f"[조달청 낙찰정보 오류] {e}")
        return []

# ============================================
# 조달청 API - 시장가격 조회
# ============================================
async def fetch_market_prices(keyword: str, price_type: str = "자재") -> list:
    type_endpoints = {
        "자재": "getStdMktPrcList",
        "시공": "getMrktStnPrcList"
    }
    
    endpoint = type_endpoints.get(price_type, "getStdMktPrcList")
    url = f"https://apis.data.go.kr/1230000/PriceInfoService/{endpoint}"
    
    params = {
        "ServiceKey": PUBLIC_DATA_API_KEY,
        "pageNo": 1,
        "numOfRows": 20,
        "type": "json",
        "prdctNm": keyword
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("response", {}).get("body", {}).get("items", [])
            if not items:
                return []
            prices = []
            for item in items:
                price = {
                    "product_name": item.get("prdctNm", ""),
                    "spec": item.get("sstdNm", ""),
                    "unit": item.get("untNm", ""),
                    "price": item.get("bsePrc", 0),
                    "effective_date": item.get("aplcDt", "")
                }
                prices.append(price)
            return prices
    except Exception as e:
        print(f"[조달청 가격정보 오류] {e}")
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

반드시 아래 JSON 배열 형식으로만 답변하세요:
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
5. 기대 효과"""
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

발표자료는 10-15장 분량으로 구성해주세요."""
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

## 응답 형식 (반드시 JSON으로)
{
  "n2b": {
    "not": "~이 아니라",
    "but": "~이다", 
    "because": "~때문이다"
  },
  "suggestion": "[목표]를 위해서는 [행동]을 해야 합니다.",
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
# wise-bid용 Claude 함수들
# ============================================
async def analyze_bid_price_with_claude(req: BidPriceAnalyzeRequest, winning_bids: list) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    if winning_bids:
        rates = [b["winning_rate"] for b in winning_bids if b["winning_rate"] > 0]
        avg_rate = sum(rates) / len(rates) if rates else 0
        min_rate = min(rates) if rates else 0
        max_rate = max(rates) if rates else 0
        winning_info = f"""
유사 입찰 낙찰률 통계 (최근 {len(winning_bids)}건):
- 평균 낙찰률: {avg_rate:.2f}%
- 최저 낙찰률: {min_rate:.2f}%
- 최고 낙찰률: {max_rate:.2f}%"""
    else:
        avg_rate = 88.0
        winning_info = "유사 입찰 데이터가 없어 일반적인 낙찰률(88%)을 기준으로 분석합니다."
    
    bubble_rate = ((req.estimated_price - req.our_cost) / req.estimated_price * 100) if req.estimated_price > 0 else 0
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""입찰 가격 N2B 분석을 해주세요.

입찰 정보:
- 공고명: {req.bid_name}
- 입찰 유형: {req.bid_type}
- 예정가격: {req.estimated_price:,}원
- 우리 원가: {req.our_cost:,}원
- 거품률: {bubble_rate:.1f}%
{winning_info}

사용자 입력 N2B:
- NOT: {req.n2b_not or '(미입력)'}
- BUT: {req.n2b_but or '(미입력)'}
- BECAUSE: {req.n2b_because or '(미입력)'}

다음 JSON 형식으로 분석 결과를 제공해주세요:
{{
  "n2b": {{
    "not": "이 예정가격은 ~이 아니다 (거품 분석)",
    "but": "적정 가격은 ~이다",
    "because": "왜냐하면 ~때문이다"
  }},
  "analysis": {{
    "bubble_rate": {bubble_rate:.1f},
    "bubble_analysis": "거품 분석 설명",
    "recommended_min": 추천최저투찰가숫자,
    "recommended_max": 추천최고투찰가숫자,
    "recommended_rate": 추천투찰률숫자,
    "strategy": "투찰 전략 설명"
  }},
  "risks": ["리스크1", "리스크2"],
  "suggestions": ["제안1", "제안2"]
}}"""
        }]
    )
    text = response.content[0].text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    
    recommended_rate = avg_rate if avg_rate > 0 else 88.0
    return {
        "n2b": {
            "not": f"예정가격 {req.estimated_price:,}원이 적정가격이 아니다",
            "but": f"원가 기반 적정가격은 {int(req.our_cost * 1.1):,}원이다",
            "because": f"거품률 {bubble_rate:.1f}%를 고려할 때 원가+10% 수준이 적정하다"
        },
        "analysis": {
            "bubble_rate": bubble_rate,
            "bubble_analysis": f"예정가격 대비 {bubble_rate:.1f}%의 거품이 존재합니다.",
            "recommended_min": int(req.estimated_price * 0.8745),
            "recommended_max": int(req.estimated_price * recommended_rate / 100),
            "recommended_rate": recommended_rate,
            "strategy": f"유사 입찰 평균 낙찰률 {recommended_rate:.1f}% 기준으로 투찰 권장"
        },
        "risks": ["경쟁 과열 시 낙찰률 하락 가능", "원가 상승 리스크"],
        "suggestions": ["경쟁업체 동향 파악", "원가 재검토"]
    }


async def analyze_bid_decision_with_claude(req: BidDecisionRequest) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    profit_rate = ((req.estimated_price - req.our_cost) / req.our_cost * 100) if req.our_cost > 0 else 0
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""입찰 참여 의사결정을 N2B 프레임워크로 분석해주세요.

입찰 정보:
- 공고명: {req.bid_name}
- 예정가격: {req.estimated_price:,}원
- 우리 원가: {req.our_cost:,}원
- 예상 수익률: {profit_rate:.1f}%

참여 이유: {req.pros}
불참 이유: {req.cons}

다음 JSON 형식으로 의사결정 분석을 제공해주세요:
{{
  "decision": "참여" 또는 "불참" 또는 "조건부 참여",
  "confidence": 확신도0에서100,
  "n2b": {{
    "not": "단순히 ~때문에 참여/불참하는 것이 아니다",
    "but": "진짜 판단 기준은 ~이다",
    "because": "왜냐하면 ~때문이다"
  }},
  "key_factors": ["핵심 판단 요소1", "핵심 판단 요소2"],
  "conditions": ["이 조건이면 참여", "이 조건이면 불참"],
  "action_items": ["실행 항목1", "실행 항목2"]
}}"""
        }]
    )
    text = response.content[0].text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    
    decision = "참여" if profit_rate > 10 else "조건부 참여" if profit_rate > 5 else "불참"
    return {
        "decision": decision,
        "confidence": 70,
        "n2b": {
            "not": "단순히 수익률만 보고 판단하는 것이 아니다",
            "but": f"종합적으로 {decision}이 적절하다",
            "because": f"예상 수익률 {profit_rate:.1f}%와 리스크를 고려했기 때문이다"
        },
        "key_factors": ["수익률", "경쟁 강도", "리소스 가용성"],
        "conditions": ["수익률 10% 이상 확보 시 참여"],
        "action_items": ["상세 원가 검토", "경쟁업체 분석"]
    }


# ============================================
# wise-bid 입찰공고 매칭용 Claude 함수들
# ============================================
async def analyze_bid_needs_with_claude(company_info: str, preferred_type: str, budget_range: str) -> dict:
    """회사 역량/관심분야를 N2B로 분석하고 입찰 검색 키워드 추출"""
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""다음 회사 정보를 바탕으로 N2B 분석과 적합한 입찰공고 검색 키워드를 추출해주세요.

회사 역량/관심분야:
{company_info}

선호 입찰 유형: {preferred_type}
선호 예산 규모: {budget_range or '제한 없음'}

N2B 관점에서 분석해주세요:
- NOT: 이 회사가 피해야 할 입찰 유형 (역량과 맞지 않는 것)
- BUT: 이 회사에 적합한 입찰 유형 (강점을 살릴 수 있는 것)
- BECAUSE: 그 이유 (핵심 역량, 실적, 차별화 요소)

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "n2b": {{
    "not": "이 회사는 ~한 입찰은 피해야 한다",
    "but": "~한 입찰에 집중해야 한다",
    "because": "왜냐하면 ~한 강점이 있기 때문이다"
  }},
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
  "recommended_types": ["물품", "용역"],
  "strengths": ["강점1", "강점2"],
  "advice": "입찰 전략 조언"
}}"""
        }]
    )
    
    text = response.content[0].text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    return {
        "n2b": {"not": "분석 실패", "but": "", "because": ""},
        "keywords": [],
        "recommended_types": [preferred_type] if preferred_type != "전체" else ["물품", "공사", "용역"],
        "strengths": [],
        "advice": ""
    }


async def match_bids_with_claude(n2b: dict, bids: list, keywords: list) -> list:
    """입찰공고 목록에서 적합한 공고를 선별하고 점수 매기기"""
    if not bids:
        return []
    
    candidates = bids[:30]
    
    def format_price(price):
        try:
            return f"{int(price):,}"
        except:
            return str(price)
    
    bid_list = "\n".join([
        f"{i+1}. [{b['bid_type']}] {b['bid_name']} | {b['agency']} | 예정가: {format_price(b.get('estimated_price', 0))}원 | 마감: {b.get('deadline', '')}"
        for i, b in enumerate(candidates)
    ])
    
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""N2B 분석 결과를 바탕으로 아래 입찰공고 중 가장 적합한 5개를 선택하고 매칭 점수를 매겨주세요.

N2B 분석:
- NOT: {n2b.get('not', '')}
- BUT: {n2b.get('but', '')}
- BECAUSE: {n2b.get('because', '')}
- 검색 키워드: {', '.join(keywords)}

입찰공고 목록:
{bid_list}

반드시 아래 JSON 배열 형식으로만 답변하세요. 번호는 위 목록의 번호입니다:
[
  {{"index": 1, "fit_score": 92, "reason": "추천 이유", "risk": "주의사항"}},
  {{"index": 3, "fit_score": 87, "reason": "추천 이유", "risk": "주의사항"}}
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
                    bid = candidates[idx].copy()
                    bid["fit_score"] = item.get("fit_score", 80)
                    bid["reason"] = item.get("reason", "")
                    bid["risk"] = item.get("risk", "")
                    results.append(bid)
        except:
            pass
    
    return results


# ============================================
# API 엔드포인트
# ============================================

@app.get("/")
async def root():
    return {"status": "ok", "version": "3.3", "message": "N2B Backend + price 포맷 수정"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "biz", is_premium)
    try:
        result = await analyze_with_claude(req.worry)
        return {"success": True, "n2b": result, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/match")
async def match(req: MatchRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "biz", is_premium)
    try:
        keyword = req.keywords[0] if req.keywords else None
        bizinfo_task = fetch_bizinfo_programs(keyword)
        kstartup_task = fetch_kstartup_programs(keyword)
        bizinfo_programs, kstartup_programs = await asyncio.gather(bizinfo_task, kstartup_task)
        all_programs = bizinfo_programs + kstartup_programs
        n2b = {"not": req.n2b_not, "but": req.n2b_but, "because": req.n2b_because, "keywords": req.keywords}
        matched = await score_programs_with_claude(n2b, all_programs, req.region)
        return {"success": True, "total_fetched": len(all_programs), "bizinfo_count": len(bizinfo_programs), "kstartup_count": len(kstartup_programs), "matched": matched, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/proposal")
async def proposal(req: ProposalRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "proposal", is_premium)
    try:
        text = await generate_proposal_with_claude(req)
        return {"success": True, "content": text, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ppt-outline")
async def ppt_outline(req: PptRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "proposal", is_premium)
    try:
        text = await generate_ppt_with_claude(req)
        return {"success": True, "content": text, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/programs")
async def get_programs(keyword: Optional[str] = None):
    bizinfo = await fetch_bizinfo_programs(keyword)
    kstartup = await fetch_kstartup_programs(keyword)
    return {"bizinfo_count": len(bizinfo), "kstartup_count": len(kstartup), "total": len(bizinfo) + len(kstartup), "programs": bizinfo + kstartup}

@app.post("/api/agency-analyze")
async def agency_analyze(req: AgencyAnalyzeRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    rate_info = check_rate_limit(ip, "agency")
    try:
        result = await agency_analyze_with_claude(req.worry)
        return {"success": True, "result": result, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/agency-deepdive")
async def agency_deepdive(req: AgencyDeepDiveRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    rate_info = check_rate_limit(ip, "agency")
    try:
        result = await agency_deepdive_with_claude(req.previous_but, req.messages)
        return {"success": True, "result": result, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# wise-bid 전용 엔드포인트
# ============================================

@app.post("/api/bid-search")
async def bid_search(req: BidSearchRequest, request: Request):
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "bid", is_premium)
    try:
        bids = await fetch_bid_announcements(req.keyword, req.bid_type, req.count)
        return {"success": True, "count": len(bids), "bids": bids, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bid-winning")
async def bid_winning(req: BidSearchRequest, request: Request):
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "bid", is_premium)
    try:
        results = await fetch_winning_bids(req.keyword, req.bid_type, req.count)
        rates = [r["winning_rate"] for r in results if r["winning_rate"] > 0]
        stats = {"count": len(results), "avg_rate": round(sum(rates) / len(rates), 2) if rates else 0, "min_rate": min(rates) if rates else 0, "max_rate": max(rates) if rates else 0}
        return {"success": True, "stats": stats, "results": results, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bid-price-analyze")
async def bid_price_analyze(req: BidPriceAnalyzeRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "bid", is_premium)
    try:
        winning_bids = await fetch_winning_bids(req.bid_name, req.bid_type, 10)
        result = await analyze_bid_price_with_claude(req, winning_bids)
        return {"success": True, "result": result, "winning_bids_count": len(winning_bids), "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bid-decision")
async def bid_decision(req: BidDecisionRequest, request: Request):
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "bid", is_premium)
    try:
        result = await analyze_bid_decision_with_claude(req)
        return {"success": True, "result": result, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 입찰공고 매칭 엔드포인트
@app.post("/api/bid-analyze-needs")
async def bid_analyze_needs(req: BidAnalyzeNeedsRequest, request: Request):
    """회사 역량/관심분야를 N2B로 분석하고 입찰 검색 키워드 추출"""
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "bid", is_premium)
    try:
        result = await analyze_bid_needs_with_claude(req.company_info, req.preferred_type, req.budget_range)
        return {"success": True, "result": result, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bid-match")
async def bid_match(req: BidMatchRequest, request: Request):
    """N2B 분석 결과를 바탕으로 입찰공고 매칭"""
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "bid", is_premium)
    try:
        # 키워드별로 입찰공고 검색
        all_bids = []
        bid_types = [req.preferred_type] if req.preferred_type != "전체" else ["물품", "공사", "용역"]
        
        for keyword in req.keywords[:3]:  # 최대 3개 키워드
            for bid_type in bid_types:
                bids = await fetch_bid_announcements(keyword, bid_type, 10)
                all_bids.extend(bids)
        
        # 중복 제거
        seen = set()
        unique_bids = []
        for bid in all_bids:
            if bid["bid_no"] not in seen:
                seen.add(bid["bid_no"])
                unique_bids.append(bid)
        
        # AI 매칭
        n2b = {"not": req.n2b_not, "but": req.n2b_but, "because": req.n2b_because}
        matched = await match_bids_with_claude(n2b, unique_bids, req.keywords)
        
        return {
            "success": True,
            "total_fetched": len(unique_bids),
            "matched": matched,
            "usage": rate_info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market-price")
async def market_price(keyword: str, price_type: str = "자재"):
    try:
        prices = await fetch_market_prices(keyword, price_type)
        return {"success": True, "count": len(prices), "prices": prices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 테스트용 GET 엔드포인트
@app.get("/api/bid-test")
async def bid_test(keyword: str = "", bid_type: str = "공사", count: int = 10):
    """브라우저에서 조달청 API 테스트용"""
    try:
        bids = await fetch_bid_announcements(keyword, bid_type, count)
        return {"success": True, "count": len(bids), "keyword": keyword, "bid_type": bid_type, "bids": bids}
    except Exception as e:
        return {"success": False, "error": str(e)}

# bid-match 디버깅용 GET 엔드포인트
@app.get("/api/bid-match-test")
async def bid_match_test(keyword: str = "도로", bid_type: str = "공사"):
    """bid-match 디버깅용"""
    try:
        # 1. 입찰공고 검색
        bids = await fetch_bid_announcements(keyword, bid_type, 10)
        if not bids:
            return {"step": "fetch", "success": False, "message": "공고 검색 결과 없음"}
        
        # 2. AI 매칭 (간단한 테스트용 N2B)
        n2b = {
            "not": "대규모 공사는 피해야 한다",
            "but": "소규모 도로포장에 집중해야 한다",
            "because": "경험과 장비가 있기 때문이다"
        }
        keywords = [keyword]
        
        matched = await match_bids_with_claude(n2b, bids, keywords)
        
        return {
            "success": True,
            "fetched_count": len(bids),
            "matched_count": len(matched),
            "matched": matched
        }
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}

@app.get("/api/usage")
async def get_usage(request: Request):
    ip = get_client_ip(request)
    today = str(date.today())
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    usage = daily_usage.get(today, {}).get(ip, {"biz": 0, "proposal": 0, "agency": 0, "bid": 0})
    biz_limit = LIMITS["biz"]["premium"] if is_premium else LIMITS["biz"]["normal"]
    proposal_limit = LIMITS["proposal"]["premium"] if is_premium else LIMITS["proposal"]["normal"]
    agency_limit = LIMITS["agency"]["normal"]
    bid_limit = LIMITS["bid"]["premium"] if is_premium else LIMITS["bid"]["normal"]
    return {
        "date": today,
        "biz": {"used": usage.get("biz", 0), "limit": biz_limit, "remaining": biz_limit - usage.get("biz", 0), "tier": "premium" if is_premium else "normal"},
        "proposal": {"used": usage.get("proposal", 0), "limit": proposal_limit, "remaining": proposal_limit - usage.get("proposal", 0), "tier": "premium" if is_premium else "normal"},
        "agency": {"used": usage.get("agency", 0), "limit": agency_limit, "remaining": agency_limit - usage.get("agency", 0)},
        "bid": {"used": usage.get("bid", 0), "limit": bid_limit, "remaining": bid_limit - usage.get("bid", 0), "tier": "premium" if is_premium else "normal"}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
