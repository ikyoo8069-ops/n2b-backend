# ============================================
# N2B 백엔드 v2.0 - API 통합 버전
# 기업마당 + K-Startup 실시간 연동
# ============================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import httpx
import xml.etree.ElementTree as ET
from typing import Optional
import os
import asyncio

app = FastAPI(title="N2B Backend v2.0", description="기업마당 + K-Startup 연동")

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
# 요청/응답 모델
# ============================================
class AnalyzeRequest(BaseModel):
    apiKey: str
    proposalText: str

class MatchRequest(BaseModel):
    apiKey: str
    n2bAnalysis: dict
    useRealtime: bool = True  # 실시간 API 사용 여부

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
                program = {
                    "id": item.findtext("pblancId", ""),
                    "name": item.findtext("pblancNm", ""),
                    "agency": item.findtext("jrsdInsttNm", ""),
                    "target": item.findtext("trgetNm", ""),
                    "period": item.findtext("reqstBeginEndDe", ""),
                    "support_amount": item.findtext("sprtCn", ""),
                    "url": item.findtext("detailPageUrl", ""),
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
            
            # 응답 구조: data 배열 또는 items
            items = data.get("data", [])
            if not items:
                items = data.get("items", [])
            if items is None:
                items = []
            
            programs = []
            for item in items:
                program = {
                    "id": str(item.get("pbanc_sn", "")),
                    "name": item.get("biz_pbanc_nm", ""),  # 지원 사업 공고 명
                    "agency": item.get("excins_nm", "창업진흥원"),
                    "target": item.get("aply_trgt_ctnt", item.get("aply_trgt", "")),  # 신청 대상
                    "period": f"{item.get('pbanc_rcpt_bgng_dt', '')} ~ {item.get('pbanc_rcpt_end_dt', '')}",
                    "support_amount": item.get("supt_biz_clsfc", ""),  # 지원 분야
                    "url": item.get("detl_pg_url", ""),
                    "region": item.get("supt_regin", ""),  # 지역명
                    "recruiting": item.get("rcrt_prgs_yn", ""),  # 모집진행여부
                    "source": "K-Startup"
                }
                programs.append(program)
            
            return programs
            
    except Exception as e:
        print(f"K-Startup API 오류: {e}")
        return []

# ============================================
# 통합 검색
# ============================================
async def search_all_programs(keyword: Optional[str] = None) -> list:
    """모든 API에서 지원사업 통합 검색"""
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
    
    return all_programs

# ============================================
# API 엔드포인트
# ============================================

@app.get("/")
async def root():
    return {
        "message": "N2B Backend v2.0 - API 통합 버전",
        "apis": ["기업마당", "K-Startup"],
        "endpoints": ["/api/programs/bizinfo", "/api/programs/kstartup", "/api/programs/all"]
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
async def get_all_programs(keyword: str = None):
    """통합 검색 (기업마당 + K-Startup)"""
    programs = await search_all_programs(keyword)
    return {"count": len(programs), "programs": programs}

# ============================================
# N2B 분석 (기존 기능)
# ============================================
@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """N2B 프레임워크로 기업 분석"""
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
- N (문제점): 현재 기업이 직면한 핵심 문제
- B (해결책): 문제를 해결할 수 있는 방안
- B (근거): 왜 이 해결책이 효과적인지

JSON 형식으로만 응답:
{{"not": "...", "but": "...", "because": "..."}}"""
                }
            ]
        )
        
        return {"success": True, "result": message.content[0].text}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# N2B 기반 정책 매칭 (실시간 API 연동)
# ============================================
@app.post("/match")
async def match_programs(request: MatchRequest):
    """N2B 분석 결과 기반 지원사업 매칭"""
    try:
        # 실시간 API에서 지원사업 가져오기
        if request.useRealtime:
            all_programs = await search_all_programs()
        else:
            all_programs = []  # 기존 하드코딩 DB 사용
        
        # Claude로 매칭
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        n2b = request.n2bAnalysis
        programs_text = "\n".join([
            f"- {p['name']} ({p['agency']}): {p['target']}" 
            for p in all_programs[:50]  # 상위 50개만
        ])
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""다음 N2B 분석 결과에 가장 적합한 지원사업 3개를 추천해주세요.

N2B 분석:
- 문제점: {n2b.get('not', '')}
- 해결책: {n2b.get('but', '')}
- 근거: {n2b.get('because', '')}

현재 모집중인 지원사업:
{programs_text}

JSON 형식으로 응답:
[
  {{"name": "사업명", "agency": "기관", "reason": "추천 이유", "fit_score": 95}},
  ...
]"""
                }
            ]
        )
        
        return {
            "success": True, 
            "total_programs": len(all_programs),
            "result": message.content[0].text
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        "apis": {
            "bizinfo": "connected" if bizinfo_ok else "error",
            "kstartup": "connected" if kstartup_ok else "error"
        }
    }
