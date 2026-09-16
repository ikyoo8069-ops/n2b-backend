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

def extract_text(response) -> str:
    parts = []
    for block in (response.content or []):
        if getattr(block, "type", None) == "text":
            t = getattr(block, "text", None)
            if t:
                parts.append(t)
    return "\n".join(parts).strip()

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
# N2B 공통 규칙 (1층과 속깊은 N2B가 함께 사용)
# ============================================
N2B_CORE = """## N2B 세 마디
- NOT: 엣지에 가서 시비를 걸어라
- BUT: 나눔으로 대안을 찾아라
- BECAUSE: 사례로 증명하라

## 제1원리
모든 것은 대체 가능하다.
세상은 이미 채워져 있고, 새로 들어오는 것은 무언가를 대체하며 들어온다.
그러므로 어떤 것도 필연이 아니다.

## NOT — 엣지를 찾아 시비를 건다
엣지란 그 분야에서 지금 자리를 장악하고 있는 것이다.
표준, 관행, 당연하게 여겨지는 방식이 엣지다.

엣지의 조건 두 가지를 반드시 확인하라.
1) 장악력: 그 자리를 확실히 쥐고 있는가. 크기는 상관없다. 작아도 확실히 쥐고 있으면 엣지다.
   여럿이 나눠 쓰고 있거나 아무도 안 쓰는 자리는 엣지가 아니다.
2) 실행 가능성: 사용자가 칠 수 있는 자리인가. 남의 판이면 대장을 찾아도 못 친다.

둘 중 하나라도 없으면 어설픈 것이며 엣지가 아니다. 다시 찾아라.

사용자가 말한 증상을 부정하지 마라. 장악하고 있는 것을 부정하라.
엣지에는 장점이 있다. 장점이 있어서 그 자리를 쥐었다.
그러나 장점이 큰 만큼 단점도 크다. 그 뒷면을 짚는 것이 시비를 거는 일이다.

## BUT — 나눔으로 대안을 찾는다
엣지는 여러 가지를 한 덩어리로 묶어 쥐고 있다. 그것이 장악의 방법이자 약점이다.
뭉친 지점을 찾아 나누면, 통째로는 불가능했던 대체가 한 자리에서는 가능해진다.

나누는 축의 예:
- 시간으로 나눈다 (교차로의 뭉친 흐름 → 신호등)
- 공간으로 나눈다 (교차로의 뭉친 흐름 → 고가도로, 지하차도)
- 기능으로 나눈다 (벽의 뭉친 차단 기능 → 문, 창문)
- 관점으로 나눈다 (천동설의 중심과 운동 → 지동설)
- 상태, 조건, 주체, 책임으로 나눈다

대안은 엣지를 통째로 대체하는 것이 아니다.
나눈 자리 하나를 차지하는 것이다.

## BECAUSE — 사례로 증명한다
이유는 논리가 아니라 사례에서 나온다.
이 대체가 성립한다면 무엇이 함께 풀리는지 구체적으로 나열하라.

## 대장과 졸개
나누면 그중 하나가 나머지를 붙들고 있다. 그것이 대장이다.
졸개를 치면 하나가 풀리고, 대장을 치면 여럿이 한꺼번에 딸려온다.

## 원리 중심
개별 사례의 특수성보다 그 사례가 속한 구조를 보라.
답은 이 경우에만 통하는 처방이 아니라, 같은 구조라면 통하는 원리여야 한다.

## 문장 작성 규칙
- 짧고 단정하게 쓴다. 컨설팅 보고서투를 쓰지 않는다.
- "체계적인", "전략적인", "역량 강화" 같은 빈 말을 쓰지 않는다.
- 무엇을 무엇으로 대체하는지 구체적으로 지목한다."""


# ============================================
# Claude 호출 함수들
# ============================================
async def analyze_with_claude(worry: str) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4096,
        system="당신은 N2B 분석 엔진입니다.\n\n" + N2B_CORE,
        messages=[{
            "role": "user",
            "content": f"""기업 대표의 고민: {worry}

이 고민이 놓인 분야에서 엣지를 찾아 시비를 걸고, 나눔으로 대안을 세우시오.
그리고 정부지원사업 검색 키워드를 추출하시오.

반드시 아래 JSON 형식으로만 답변하세요. 다른 말은 쓰지 마시오:
{{
  "edge": "이 분야에서 지금 자리를 장악하고 있는 것",
  "lumped": "그 엣지가 무엇들을 한 덩어리로 묶어 쥐고 있는가",
  "divide_axis": "어떤 축으로 나누었는가",
  "not": "~을 대체 불가능하다고 여겼으나, 실은 대체 가능하다",
  "but": "나눈 자리에 ~이 들어선다",
  "because": "왜냐하면 ~때문이다",
  "keywords": ["키워드1", "키워드2", "키워드3"]
}}"""
        }]
    )
    raw = extract_text(response)
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except Exception:
            pass
    return {
        "not": "분석 실패 — AI 응답을 아래에 그대로 표시합니다",
        "but": raw[:600] if raw else "(응답이 비어 있음)",
        "because": "",
        "keywords": []
    }


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
        model="claude-sonnet-5",
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
    text = extract_text(response)
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
        model="claude-sonnet-5",
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
    return extract_text(response)


async def generate_ppt_with_claude(req: PptRequest) -> str:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-5",
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
    return extract_text(response)


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
        model="claude-sonnet-5",
        max_tokens=2048,
        system=AGENCY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": worry}]
    )
    text = extract_text(response)
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
        model="claude-sonnet-5",
        max_tokens=2048,
        system="당신은 N2B 분석 전문가입니다. 반드시 지정된 JSON 형식으로만 답변하세요.",
        messages=api_messages
    )
    text = extract_text(response)
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
        model="claude-sonnet-5",
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
    text = extract_text(response)
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
        model="claude-sonnet-5",
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
    text = extract_text(response)
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
        model="claude-sonnet-5",
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

    text = extract_text(response)
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
        model="claude-sonnet-5",
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

    text = extract_text(response)
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
    return {"status": "ok", "version": "3.4", "message": "N2B Backend + 엣지/나눔 규칙 적용"}

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


# ============================================
# 속깊은 N2B (Deep N2B)
# NOT  엣지에 가서 시비를 걸어라
# BUT  나눔으로 대안을 찾아라
# BECAUSE  사례로 증명하라
# ============================================
class DeepDiveRequest(BaseModel):
    worry: str
    layer: int = 1
    history: list = []
    answer: str = ""
    best: dict = {}
    domain: str = "기업경영"


DEEP_N2B_RULES = """당신은 N2B 분석 엔진입니다.

""" + N2B_CORE + """

## 층
한 층의 BECAUSE 안에는 또 당연하게 여겨지는 것이 있다.
그것을 다시 엣지로 보고 시비를 걸면 다음 층이 열린다.
대체는 끝이 없으므로 멈출 곳을 찾을 수는 없다. 어느 층이 대장인지 견줄 수 있을 뿐이다.

## 판정
resolved: 이 대체로 함께 풀리는 것들을 구체적으로 나열한다
utility: 0~100. 대장을 쳤으면 높고, 졸개를 쳤으면 낮다
  - 실행할 수 없는 대체는 아무것도 풀지 못하므로 낮다
  - 하나만 푸는 대체는 아무리 뜻밖이어도 낮다
  - 여러 개가 한꺼번에 딸려오는 대체가 높다

## 되물음
다음 층으로 내려가려면 사용자에게서 새 정보가 필요하다.
추측으로 채우지 말고, 이 층에서 갈라지는 지점을 묻는 질문 하나를 만들어라.
선택지는 2~3개, 서로 확실히 다른 방향이어야 한다.

## 되물음 금지사항 (반드시 지킬 것)
절대 묻지 말 것: 금액, 매출액, 자산, 부채 등 구체적 수치 / 기업명, 거래처명, 인물명 / 계약 내용, 기술 세부사항, 내부 문서

구조와 방향만 물을 것:
- 나쁜 예: "월 매출이 얼마입니까?"  좋은 예: "매출이 늘고 있습니까, 줄고 있습니까?"
- 나쁜 예: "주요 거래처가 어디입니까?"  좋은 예: "거래처가 한 곳에 몰려 있습니까, 분산되어 있습니까?"

## 출력 규칙
반드시 JSON 하나만 출력한다. 설명, 머리말, 코드블록 표시를 붙이지 않는다.
각 항목은 한 문장으로 짧게 쓴다. resolved는 3개 이내로 쓴다."""


def _parse_json_block(text: str, array: bool = False):
    pattern = r'\[[\s\S]*\]' if array else r'\{[\s\S]*\}'
    m = re.search(pattern, text or "")
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        return None


async def deep_n2b_layer(req: DeepDiveRequest) -> dict:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    history_text = ""
    for h in req.history:
        history_text += f"\n[{h.get('layer')}층]\n"
        if h.get("edge"):
            history_text += f"엣지: {h.get('edge')}\n"
        history_text += f"NOT: {h.get('not','')}\n"
        history_text += f"BUT: {h.get('but','')}\n"
        history_text += f"BECAUSE: {h.get('because','')}\n"
        history_text += f"함께 풀리는 것: {', '.join(h.get('resolved', []))}\n"
        if h.get("question"):
            history_text += f"물음: {h.get('question')}\n"
        if h.get("answer"):
            history_text += f"답변: {h.get('answer')}\n"

    best_text = "없음"
    if req.best:
        best_text = (f"{req.best.get('layer')}층 / "
                     f"NOT: {req.best.get('not','')} / "
                     f"utility {req.best.get('utility',0)}")

    prompt = f"""분석 영역: {req.domain}
원래 고민: {req.worry}

지금까지의 층:{history_text if history_text else " (없음, 이번이 1층)"}

현재 가장 실용적인 층: {best_text}

방금 사용자가 답한 내용: {req.answer or "(없음)"}

이제 {req.layer}층의 N2B를 만드시오.
{"이전 층의 BECAUSE 안에서 아직 당연하게 여겨지는 것을 찾아, 그것을 엣지로 보고 시비를 걸며 한 층 더 내려가시오." if req.layer > 1 else ""}

JSON 하나만 출력하시오:
{{
  "layer": {req.layer},
  "edge": "이 층의 엣지 — 지금 그 자리를 장악하고 있는 것",
  "edge_grip": "그 엣지가 어떻게 자리를 쥐고 있는가",
  "lumped": "그 엣지가 무엇들을 한 덩어리로 묶어 쥐고 있는가",
  "divide_axis": "어떤 축으로 나누었는가",
  "not": "~을 대체 불가능하다고 여겼으나, 실은 대체 가능하다",
  "but": "나눈 자리에 ~이 들어선다",
  "because": "왜냐하면 ~때문이다",
  "resolved": ["함께 풀리는 것1", "함께 풀리는 것2", "함께 풀리는 것3"],
  "utility": 70,
  "utility_reason": "이 점수를 준 이유 한 문장",
  "question": "다음 층으로 가기 위해 사용자에게 묻는 질문",
  "options": ["선택지1", "선택지2", "선택지3"],
  "info_exhausted": false
}}"""

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=8192,
        system=DEEP_N2B_RULES,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = extract_text(response)
    data = _parse_json_block(raw)
    if not data:
        return {
            "layer": req.layer,
            "not": "분석 실패 — AI 응답을 아래에 그대로 표시합니다",
            "but": raw[:600] if raw else "(응답이 비어 있음)",
            "because": "",
            "resolved": [],
            "utility": 0,
            "utility_reason": "응답을 해석하지 못했습니다",
            "question": "",
            "options": [],
            "info_exhausted": True
        }
    data["layer"] = req.layer
    data.setdefault("resolved", [])
    data.setdefault("utility", 0)
    return data


def pick_best(current: dict, best: dict) -> dict:
    if not best:
        return current
    if current.get("utility", 0) > best.get("utility", 0):
        return current
    return best


MAX_LAYER = 4
NO_GAIN_LIMIT = 2


@app.post("/api/deepdive")
async def deepdive(req: DeepDiveRequest, request: Request):
    """속깊은 N2B — 한 층씩 내려가며 가장 실용적인 대체를 찾는다"""
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "biz", is_premium)

    try:
        layer_result = await deep_n2b_layer(req)

        prev_best = req.best or {}
        new_best = dict(pick_best(layer_result, prev_best))
        gained = new_best.get("layer") == layer_result.get("layer")

        no_gain = 0 if gained else int(prev_best.get("_no_gain", 0)) + 1
        new_best["_no_gain"] = no_gain

        stop = False
        stop_reason = ""
        if req.layer >= MAX_LAYER:
            stop, stop_reason = True, f"{MAX_LAYER}층까지 내려왔습니다"
        elif no_gain >= NO_GAIN_LIMIT:
            stop, stop_reason = True, "더 내려가도 함께 풀리는 양이 늘지 않습니다"
        elif layer_result.get("info_exhausted"):
            stop, stop_reason = True, "더 파고들 정보가 없습니다"
        elif not layer_result.get("question"):
            stop, stop_reason = True, "더 물을 것이 없습니다"

        return {
            "success": True,
            "layer": layer_result,
            "best": new_best,
            "stop": stop,
            "stop_reason": stop_reason,
            "next_layer": req.layer + 1,
            "usage": rate_info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# wise-expert — 전문가 이력에서 학회 공동사업 기획
# ============================================
class ExpertTraceRequest(BaseModel):
    profile: str
    interest: str = ""
    regret: str = ""
    society: str = "한국자산관리학회"
    society_scope: str = "경영·기술·금융·부동산·데이터 및 유·무형 자산관리 전반. SOC(도로·철도·항만·지하시설물·상하수도·가스·환경), 에너지(화력·수력·원자력·발전기술·운영·송전·배전), 산업(석유화학·반도체·자동차·고무·IT·철강·조선·어선·안전)"


class ExpertDraftRequest(BaseModel):
    profile: str
    trace: str = ""
    topic: str = ""
    edge: str = ""
    lumped: str = ""
    divide_axis: str = ""
    alternative: str = ""
    why_together: str = ""
    need_expertise: list = []
    society: str = "한국자산관리학회"


EXPERT_RULES = """당신은 N2B 기반 사업기획 엔진입니다.

""" + N2B_CORE + """

## 이 작업의 특수 조건
전문가 개인의 과제를 만드는 것이 아니다.
그 전문가와 학회가 함께 해야만 가능한 사업을 기획하는 것이다.

따라서 엣지는 다음 자리에서 찾아야 한다.
- 그 전문가의 전문성과 학회의 자산관리 영역이 겹치는 자리
- 학회가 함께함으로써 풀리는 양이 늘어나는 것만 남긴다
- 전문가가 혼자 해도 같은 결과가 나오는 것은 제외한다

판정 기준: 혼자 할 때보다 함께 할 때 풀리는 양이 늘어나는가.
늘지 않으면 그것은 개인 과제이며 이 기획의 대상이 아니다.

학회가 함께하는 이유는 전문가의 부족을 메우는 것이 아니다.
학회는 회계·세무·법률·기술·부동산·데이터의 전문성과 학술 검증 체계, 그리고
공공·산업계 발주처에 대한 공신력을 가지고 있다.
전문가 한 사람의 판단이 학회를 거치면 검증된 판단이 되고,
개인의 제안이 학회 이름으로 나가면 발주처가 받을 수 있는 제안이 된다.
그 차이를 구체적으로 적어라. "시너지" 같은 빈 말로 적지 마라.

## 대체의 궤적
전문가의 이력은 그가 무엇을 대체해왔는지의 기록이다.
논문, 특허, 수행 과제, 개발 기술, 상훈을 읽고 그 궤적을 찾아라.
궤적이 보이면 다음에 대체할 자리가 보인다.

이력에 없는 것은 추측하지 마라.
추측이 필요한 대목은 따로 표시하여 본인 확인을 요청한다.

## 문장 작성 규칙
- 짧고 단정하게. 컨설팅 보고서투를 쓰지 않는다.
- "체계적", "전략적", "역량 강화", "시너지" 같은 빈 말을 쓰지 않는다.
- 무엇을 무엇으로 대체하는지 구체적으로 지목한다.
- 반드시 JSON 하나만 출력한다. 설명이나 코드블록 표시를 붙이지 않는다."""


@app.post("/api/expert-trace")
async def expert_trace(req: ExpertTraceRequest, request: Request):
    """전문가 이력에서 대체의 궤적을 읽고, 학회와 함께 할 사업 후보를 뽑는다"""
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "proposal", is_premium)

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=8192,
            system=EXPERT_RULES,
            messages=[{
                "role": "user",
                "content": f"""## 전문가 이력·포트폴리오
{req.profile}

## 지금 관심 있는 것
{req.interest or "(미입력)"}

## 최근 아쉬웠던 것
{req.regret or "(미입력)"}

## 학회
{req.society}
활동 영역: {req.society_scope}

---

이 전문가의 이력을 읽고 대체의 궤적을 찾으시오.
그리고 그 궤적과 학회의 자산관리 영역이 겹치는 자리에서 엣지를 찾아,
학회와 함께 해야만 가능한 사업 후보 3개를 제시하시오.

JSON 하나만 출력하시오:
{{
  "trace": "이 전문가가 무엇을 무엇으로 대체해왔는가 — 두세 문장",
  "trace_evidence": ["궤적의 근거가 되는 이력 항목1", "항목2", "항목3"],
  "core_strength": "다른 사람이 갖기 어려운 이 전문가만의 자리 한 문장",
  "overlap": "이 전문성과 자산관리가 겹치는 자리",
  "candidates": [
    {{
      "title": "사업 후보 이름",
      "edge": "이 사업이 시비를 거는 엣지 — 지금 그 자리를 장악하고 있는 것",
      "lumped": "그 엣지가 무엇들을 한 덩어리로 묶어 쥐고 있는가",
      "divide_axis": "어떤 축으로 나누는가",
      "alternative": "나눈 자리에 무엇이 들어서는가",
      "resolved": ["함께 풀리는 것1", "함께 풀리는 것2", "함께 풀리는 것3"],
      "why_together": "학회가 함께하면 무엇이 더 되는가 — 혼자일 때와 무엇이 달라지는가",
      "need_expertise": ["필요한 다른 전문분야1", "분야2"],
      "utility": 70
    }}
  ],
  "to_confirm": ["이력만으로는 알 수 없어 본인 확인이 필요한 것1", "것2", "것3"]
}}"""
            }]
        )
        raw = extract_text(response)
        data = _parse_json_block(raw)
        if not data:
            return {"success": False, "raw": raw[:1500], "message": "응답을 해석하지 못했습니다", "usage": rate_info}
        data.setdefault("candidates", [])
        data.setdefault("to_confirm", [])
        return {"success": True, "result": data, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/expert-draft")
async def expert_draft(req: ExpertDraftRequest, request: Request):
    """선택한 사업 후보로 기획서 초안을 작성한다"""
    if not CLAUDE_API_KEY:
        raise HTTPException(status_code=500, detail="CLAUDE_API_KEY가 설정되지 않았습니다")
    ip = get_client_ip(request)
    is_premium = request.headers.get("x-premium-key") == PREMIUM_KEY
    rate_info = check_rate_limit(ip, "proposal", is_premium)

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=8192,
            system=EXPERT_RULES,
            messages=[{
                "role": "user",
                "content": f"""## 전문가 이력·포트폴리오
{req.profile}

## 대체의 궤적
{req.trace or "(미확인)"}

## 선택한 사업
- 사업명: {req.topic}
- 엣지: {req.edge}
- 뭉쳐 있는 것: {req.lumped}
- 나눈 축: {req.divide_axis}
- 들어설 대안: {req.alternative}
- 학회가 함께하면 더 되는 것: {req.why_together}
- 필요한 다른 전문분야: {', '.join(req.need_expertise) if req.need_expertise else "(미정)"}

## 학회
{req.society}

---

이 사업의 기획서 초안을 작성하시오.
전문가에게 보내어 심층 검토를 요청할 문서다.
따라서 완성본이 아니라 **고칠 데가 보이는 초안**이어야 한다.
추측으로 채운 대목은 숨기지 말고 to_confirm에 적어 본인 확인을 요청하라.

JSON 하나만 출력하시오:
{{
  "title": "사업명",
  "one_line": "이 사업을 한 문장으로",
  "background": "추진 배경 — 지금 무엇이 그 자리를 장악하고 있는가 (3~4문장)",
  "necessity": "필요성 — 그 장악이 무엇을 한 덩어리로 묶어 쥐고 있어 무엇이 막히는가 (3~4문장)",
  "problem": "문제 정의 — N2B 형식 세 문장으로. NOT/BUT/BECAUSE를 각각 한 문장",
  "objective": "사업 목표 — 무엇을 무엇으로 대체하는가 (2~3문장)",
  "scope": ["수행 범위 항목1", "항목2", "항목3", "항목4"],
  "roles": [
    {{"who": "전문가 본인", "what": "맡을 역할"}},
    {{"who": "학회", "what": "맡을 역할"}},
    {{"who": "필요한 다른 전문분야", "what": "맡을 역할"}}
  ],
  "expected": ["기대 효과1", "기대 효과2", "기대 효과3"],
  "funding_route": ["연계 가능한 사업·발주처 후보1", "후보2"],
  "to_confirm": ["본인 확인이 필요한 것1", "것2", "것3", "것4"],
  "next_step": "이 초안을 받은 전문가가 바로 할 수 있는 다음 행동 한 문장"
}}"""
            }]
        )
        raw = extract_text(response)
        data = _parse_json_block(raw)
        if not data:
            return {"success": False, "raw": raw[:1500], "message": "응답을 해석하지 못했습니다", "usage": rate_info}
        return {"success": True, "result": data, "usage": rate_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
