# ============================================
# N2B 백엔드 v3.0 - 키워드 + 지역 + 예상공고
# 기업마당 + K-Startup 실시간 연동
# ============================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import httpx
import xml.etree.ElementTree as ET
from typing import Optional, List
import os
import asyncio
import json
import re

app = FastAPI(title="N2B Backend v3.0", description="키워드 + 지역 + 예상공고")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# API 키 설정 (환경변수 또는 기본값)
# ============================================
BIZINFO_API_KEY = os.getenv("BIZINFO_API_KEY", "f41G7V")
KSTARTUP_API_KEY = os.getenv("KSTARTUP_API_KEY", "47bd938c975a8989c5561a813fe66fcd68b76bfc4b4d54ca33345923b5b51897")

# ============================================
# 반복 사업 패턴 (예상 공고용)
# ============================================
RECURRING_PROGRAMS = [
    {
        "name": "스마트공장 구축 지원사업",
        "agency": "중소벤처기업부",
        "expected_month": "2월",
        "category": "제조/스마트공장",
        "keywords": ["스마트공장", "제조", "자동화", "IoT"]
    },
    {
        "name": "창업성장기술개발사업",
        "agency": "중소벤처기업부",
        "expected_month": "2월",
        "category": "R&D/기술개발",
        "keywords": ["창업", "기술개발", "R&D", "스타트업"]
    },
    {
        "name": "농식품 벤처창업 지원",
        "agency": "농림축산식품부",
        "expected_month": "3월",
        "category": "농업/스마트팜",
        "keywords": ["농업", "스마트팜", "식품", "농식품"]
    },
    {
        "name": "ICT 융합 스마트팜 지원",
        "agency": "과학기술정보통신부",
        "expected_month": "3월",
        "category": "농업/스마트팜",
        "keywords": ["스마트팜", "ICT", "IoT", "농업"]
    },
    {
        "name": "AI 바우처 지원사업",
        "agency": "과학기술정보통신부",
        "expected_month": "2월",
        "category": "AI/데이터",
        "keywords": ["AI", "인공지능", "데이터", "머신러닝"]
    },
    {
        "name": "데이터 바우처 지원사업",
        "agency": "과학기술정보통신부",
        "expected_month": "3월",
        "category": "AI/데이터",
        "keywords": ["데이터", "빅데이터", "분석"]
    },
    {
        "name": "청년창업사관학교",
        "agency": "중소벤처기업부",
        "expected_month": "1월",
        "category": "창업지원",
        "keywords": ["청년", "창업", "사관학교"]
    },
    {
        "name": "초기창업패키지",
        "agency": "창업진흥원",
        "expected_month": "2월",
        "category": "창업지원",
        "keywords": ["초기창업", "스타트업", "창업"]
    },
    {
        "name": "그린뉴딜 스타트업 지원",
        "agency": "환경부",
        "expected_month": "3월",
        "category": "환경/에너지",
        "keywords": ["그린", "환경", "에너지", "탄소"]
    },
    {
        "name": "헬스케어 스타트업 육성",
        "agency": "보건복지부",
        "expected_month": "4월",
        "category": "헬스케어",
        "keywords": ["헬스케어", "의료", "바이오", "건강"]
    },
    {
        "name": "소재부품장비 기술개발",
        "agency": "산업통상자원부",
        "expected_month": "2월",
        "category": "제조/소부장",
        "keywords": ["소재", "부품", "장비", "제조"]
    },
    {
        "name": "수출바우처 지원사업",
        "agency": "KOTRA",
        "expected_month": "1월",
        "category": "수출/해외진출",
        "keywords": ["수출", "해외", "글로벌", "마케팅"]
    }
]

# ============================================
# 요청/응답 모델
# ============================================
class AnalyzeRequest(BaseModel):
    apiKey: str
    proposalText: str

class MatchRequest(BaseModel):
    apiKey: str
    n2bAnalysis: dict
    region: str = "전체"
    useRealtime: bool = True

# ============================================
# 기업마당 API
# ============================================
async def fetch_bizinfo_programs(keyword: Optional[str] = None, count: int = 100) -> list:
    """기업마당에서 지원사업 목록 조회"""
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
                    "support_amount": item.findtext("sprtCn", ""),
                    "url": f"https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId={pblanc_id}" if pblanc_id else "",
                    "region": item.findtext("jrsdInsttNm", "전국"),  # 지역 정보
                    "source": "기업마당"
                }
                programs.append(program)
            
            return programs
            
    except Exception as e:
        print(f"기업마당 API 오류: {e}")
        return []

# ============================================
# K-Startup API
# ============================================
async def fetch_kstartup_programs(keyword: Optional[str] = None, page: int = 1, per_page: int = 100) -> list:
    """K-Startup에서 창업지원사업 목록 조회"""
    url = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
    
    params = {
        "ServiceKey": KSTARTUP_API_KEY,
        "page": page,
        "perPage": per_page,
        "returnType": "json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            items = data.get("data", [])
            if not items:
                items = data.get("items", [])
            if items is None:
                items = []
            
            programs = []
            for item in items:
                program = {
                    "id": str(item.get("pbanc_sn", "")),
                    "name": item.get("biz_pbanc_nm", ""),
                    "agency": item.get("excins_nm", "창업진흥원"),
                    "target": item.get("aply_trgt_ctnt", item.get("aply_trgt", "")),
                    "period": f"{item.get('pbanc_rcpt_bgng_dt', '')} ~ {item.get('pbanc_rcpt_end_dt', '')}",
                    "support_amount": item.get("supt_biz_clsfc", ""),
                    "url": item.get("detl_pg_url", ""),
                    "region": item.get("supt_regin", "전국"),
                    "recruiting": item.get("rcrt_prgs_yn", ""),
                    "source": "K-Startup"
                }
                programs.append(program)
            
            return programs
            
    except Exception as e:
        print(f"K-Startup API 오류: {e}")
        return []

# ============================================
# 지역 키워드 목록 (다른 지역 제외용)
# ============================================
REGION_KEYWORDS = {
    "서울": ["서울", "강남", "강북", "마포", "송파", "영등포"],
    "부산": ["부산", "해운대", "동래"],
    "대구": ["대구", "수성", "달서"],
    "인천": ["인천", "연수", "부평"],
    "광주": ["광주"],
    "대전": ["대전", "유성", "서구"],
    "울산": ["울산"],
    "세종": ["세종"],
    "경기": ["경기", "수원", "성남", "고양", "용인", "안양", "안산", "화성", "평택", "시흥", "파주", "김포", "광명", "군포", "오산", "이천", "안성", "의왕", "하남", "여주", "양평", "동두천", "과천", "구리", "남양주", "의정부", "포천"],
    "강원": ["강원", "춘천", "원주", "강릉", "동해", "속초"],
    "충북": ["충북", "청주", "충주", "제천"],
    "충남": ["충남", "천안", "아산", "공주", "논산", "서산", "당진"],
    "전북": ["전북", "전주", "익산", "군산", "정읍"],
    "전남": ["전남", "목포", "여수", "순천", "광양"],
    "경북": ["경북", "포항", "경주", "구미", "김천", "안동", "영주"],
    "경남": ["경남", "창원", "진주", "김해", "양산", "거제", "통영"],
    "제주": ["제주", "서귀포"]
}

def get_other_regions(selected_region: str) -> list:
    """선택한 지역 외 다른 지역 키워드 목록 반환"""
    other_keywords = []
    for region, keywords in REGION_KEYWORDS.items():
        if region != selected_region:
            other_keywords.extend(keywords)
    return other_keywords

def contains_other_region(name: str, selected_region: str) -> bool:
    """사업명에 다른 지역 키워드가 포함되어 있는지 확인"""
    other_keywords = get_other_regions(selected_region)
    name_lower = name.lower()
    for keyword in other_keywords:
        if keyword in name_lower:
            return True
    return False

def is_nationwide_program(name: str, agency: str) -> bool:
    """전국 사업인지 확인 (중앙부처 사업)"""
    nationwide_agencies = [
        "중소벤처기업부", "과학기술정보통신부", "산업통상자원부", 
        "농림축산식품부", "환경부", "보건복지부", "고용노동부",
        "창업진흥원", "중소기업진흥공단", "KOTRA", "정보통신산업진흥원",
        "한국산업기술진흥원", "한국에너지공단"
    ]
    for na in nationwide_agencies:
        if na in agency:
            return True
    return False

# ============================================
# 통합 검색 (지역 필터링 강화)
# ============================================
async def search_all_programs(keyword: Optional[str] = None, region: str = "전체") -> list:
    """모든 API에서 지원사업 통합 검색 + 지역 필터링 (강화)"""
    bizinfo_task = fetch_bizinfo_programs(keyword)
    kstartup_task = fetch_kstartup_programs(keyword)
    
    bizinfo_results, kstartup_results = await asyncio.gather(
        bizinfo_task, 
        kstartup_task,
        return_exceptions=True
    )
    
    all_programs = []
    
    if isinstance(bizinfo_results, list):
        all_programs.extend(bizinfo_results)
    
    if isinstance(kstartup_results, list):
        all_programs.extend(kstartup_results)
    
    # 지역 필터링: 특정 지역 선택 시
    if region != "전체":
        filtered = []
        selected_keywords = REGION_KEYWORDS.get(region, [region])
        
        for p in all_programs:
            name = p.get("name", "")
            agency = p.get("agency", "")
            p_region = p.get("region", "")
            
            # 1. 중앙부처 전국 사업 → 포함
            if is_nationwide_program(name, agency):
                # 단, 사업명에 다른 지역 키워드가 있으면 제외
                if not contains_other_region(name, region):
                    filtered.append(p)
                continue
            
            # 2. 선택한 지역 키워드가 사업명/지역에 포함 → 포함
            for kw in selected_keywords:
                if kw in name or kw in p_region:
                    filtered.append(p)
                    break
            else:
                # 3. 다른 지역 키워드가 없고 지역 정보도 없으면 → 전국으로 간주
                if not contains_other_region(name, region) and not p_region:
                    filtered.append(p)
        
        return filtered
    
    return all_programs

# ============================================
# 예상 공고 매칭
# ============================================
def get_expected_programs(keywords: List[str]) -> list:
    """키워드 기반 예상 공고 추천"""
    expected = []
    
    for program in RECURRING_PROGRAMS:
        # 키워드 매칭
        match_count = 0
        for kw in keywords:
            for prog_kw in program["keywords"]:
                if kw.lower() in prog_kw.lower() or prog_kw.lower() in kw.lower():
                    match_count += 1
                    break
        
        if match_count > 0:
            expected.append({
                "name": program["name"],
                "agency": program["agency"],
                "expected_month": f"2026년 {program['expected_month']}",
                "category": program["category"],
                "match_score": min(95, 70 + match_count * 10),
                "type": "expected"
            })
    
    # 매칭 점수 순 정렬
    expected.sort(key=lambda x: x["match_score"], reverse=True)
    return expected[:5]  # 상위 5개

# ============================================
# API 엔드포인트
# ============================================

@app.get("/")
async def root():
    return {
        "message": "N2B Backend v3.0 - 키워드 + 지역 + 예상공고",
        "apis": ["기업마당", "K-Startup"],
        "features": ["키워드 추출", "지역 필터링", "예상 공고 추천"]
    }

@app.get("/api/programs/bizinfo")
async def get_bizinfo_programs(keyword: str = None, count: int = 100):
    """기업마당 지원사업 조회"""
    programs = await fetch_bizinfo_programs(keyword, count)
    return {"source": "기업마당", "count": len(programs), "programs": programs}

@app.get("/api/programs/kstartup")
async def get_kstartup_programs(keyword: str = None, page: int = 1):
    """K-Startup 창업지원사업 조회"""
    programs = await fetch_kstartup_programs(keyword, page)
    return {"source": "K-Startup", "count": len(programs), "programs": programs}

@app.get("/api/programs/all")
async def get_all_programs(keyword: str = None, region: str = "전체"):
    """통합 검색 (기업마당 + K-Startup) + 지역 필터"""
    programs = await search_all_programs(keyword, region)
    return {"count": len(programs), "region": region, "programs": programs}

# ============================================
# N2B 분석 (키워드 추출 추가)
# ============================================
@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """N2B 프레임워크로 기업 분석 + 키워드 추출"""
    try:
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""다음 기업 정보를 N2B 프레임워크로 분석해주세요.

기업 정보:
{request.proposalText}

N2B 분석:
- N (Not/문제점): 현재 기업이 직면한 핵심 문제
- B (But/해결책): 문제를 해결할 수 있는 방안
- B (Because/근거): 왜 이 해결책이 효과적인지
- 키워드: 정부지원사업 검색에 활용할 핵심 키워드 5개

JSON 형식으로만 응답 (다른 텍스트 없이):
{{"not": "...", "but": "...", "because": "...", "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]}}"""
                }
            ]
        )
        
        return {"success": True, "result": message.content[0].text}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# N2B 기반 정책 매칭 (지역 + 예상공고 포함)
# ============================================
@app.post("/match")
async def match_programs(request: MatchRequest):
    """N2B 분석 결과 기반 지원사업 매칭 + 예상공고"""
    try:
        region = request.region if hasattr(request, 'region') else "전체"
        
        # 실시간 API에서 지원사업 가져오기 (지역 필터링 적용)
        if request.useRealtime:
            all_programs = await search_all_programs(region=region)
        else:
            all_programs = []
        
        # Claude로 매칭
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        n2b = request.n2bAnalysis
        keywords = n2b.get('keywords', [])
        
        programs_text = "\n".join([
            f"- {p['name']} | 기관: {p.get('agency', '')} | 기간: {p.get('period', '미정')} | URL: {p.get('url', '')}" 
            for p in all_programs[:50]
        ])
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""다음 N2B 분석 결과에 가장 적합한 지원사업 5개를 추천해주세요.

N2B 분석:
- 문제점: {n2b.get('not', '')}
- 해결책: {n2b.get('but', '')}
- 근거: {n2b.get('because', '')}
- 키워드: {', '.join(keywords) if keywords else '없음'}

현재 모집중인 지원사업 (지역: {region}):
{programs_text if programs_text else '현재 모집중인 사업이 없습니다.'}

JSON 형식으로만 응답 (다른 텍스트 없이):
[
  {{"name": "사업명", "agency": "기관", "period": "접수기간", "url": "상세페이지URL", "reason": "추천 이유", "fit_score": 95}},
  ...
]

적합한 사업이 없으면 빈 배열 []로 응답."""
                }
            ]
        )
        
        # 예상 공고 추천
        expected_programs = get_expected_programs(keywords) if keywords else []
        
        # AI 응답에서 URL 후처리 (사업명으로 원본 데이터에서 URL 매칭)
        ai_result = message.content[0].text
        try:
            json_match = re.search(r'\[[\s\S]*\]', ai_result)
            if json_match:
                matched_programs = json.loads(json_match.group())
                # 사업명으로 URL 찾아서 추가
                for mp in matched_programs:
                    for op in all_programs:
                        if mp.get('name') and op.get('name') and mp['name'] in op['name']:
                            mp['url'] = op.get('url', '')
                            mp['period'] = op.get('period', mp.get('period', ''))
                            break
                ai_result = json.dumps(matched_programs, ensure_ascii=False)
        except:
            pass  # 파싱 실패 시 원본 유지
        
        return {
            "success": True, 
            "total_programs": len(all_programs),
            "region": region,
            "result": ai_result,
            "expected_programs": expected_programs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# 예상 공고 조회
# ============================================
@app.get("/api/programs/expected")
async def get_expected_programs_api(keywords: str = ""):
    """키워드 기반 예상 공고 조회"""
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    expected = get_expected_programs(keyword_list) if keyword_list else RECURRING_PROGRAMS[:5]
    return {"count": len(expected), "programs": expected}

# ============================================
# 상태 확인
# ============================================
@app.get("/health")
async def health_check():
    """API 상태 확인"""
    bizinfo_ok = False
    kstartup_ok = False
    
    try:
        bizinfo = await fetch_bizinfo_programs(count=1)
        bizinfo_ok = len(bizinfo) > 0
    except:
        pass
    
    try:
        kstartup = await fetch_kstartup_programs(per_page=1)
        kstartup_ok = len(kstartup) > 0
    except:
        pass
    
    return {
        "status": "healthy",
        "version": "3.0",
        "apis": {
            "bizinfo": "connected" if bizinfo_ok else "error",
            "kstartup": "connected" if kstartup_ok else "error"
        },
        "features": ["keywords", "region_filter", "expected_programs"]
    }
