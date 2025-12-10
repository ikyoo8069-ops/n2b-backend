from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import anthropic
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 한국 시/도 목록
REGIONS = [
    "전체", "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"
]

class AnalyzeRequest(BaseModel):
    apiKey: str
    proposalText: str

class MatchRequest(BaseModel):
    apiKey: str
    n2bAnalysis: dict
    region: Optional[str] = "전체"

@app.get("/")
async def root():
    return {
        "message": "N2B API Server is running", 
        "version": "3.1.0 - 지역 필터링",
        "regions": REGIONS
    }

@app.get("/regions")
async def get_regions():
    """지역 목록 반환"""
    return {"regions": REGIONS}

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
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
    "keywords": ["키워드1", "키워드2", "키워드3"]
}}
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
    try:
        client = anthropic.Anthropic(api_key=request.apiKey)
        n2b = request.n2bAnalysis
        region = request.region if request.region != "전체" else ""
        
        region_filter = f"지역: {region}" if region else "전국"
        
        search_message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search"
            }],
            messages=[{
                "role": "user",
                "content": f"""다음 N2B 분석 결과를 바탕으로, 현재 모집중인 정부지원사업을 검색해주세요.

N2B 분석:
- N (문제점): {n2b['N']}
- B (솔루션): {n2b['B']}
- C (근거): {n2b['C']}
- 키워드: {', '.join(n2b.get('keywords', []))}

🎯 지역 필터: {region_filter}

bizinfo.go.kr 또는 k-startup.go.kr에서 {region_filter} 관련 현재 모집중인 정부지원사업을 검색해주세요.

결과는 다음 JSON 형식으로 반환해주세요:
{{
    "programs": [
        {{
            "name": "사업명",
            "organization": "주관기관",
            "region": "지역",
            "deadline": "마감일",
            "amount": "지원금액",
            "url": "상세링크",
            "matchScore": 0-100,
            "matchReason": "N2B 매칭 이유"
        }}
    ],
    "searchDate": "검색일시",
    "regionFilter": "{region_filter}"
}}
"""
            }]
        )
        
        result_text = ""
        for block in search_message.content:
            if hasattr(block, 'text'):
                result_text += block.text
        
        result_text = result_text.replace("```json", "").replace("```", "").strip()
        
        try:
            result = json.loads(result_text)
        except:
            result = {
                "programs": [],
                "searchDate": "",
                "regionFilter": region_filter,
                "rawResponse": result_text
            }
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
