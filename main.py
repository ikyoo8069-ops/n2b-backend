from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import anthropic
import json
import traceback

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "version": "3.1.0",
        "regions": REGIONS
    }

@app.get("/regions")
async def get_regions():
    return {"regions": REGIONS}

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    try:
        if not request.apiKey or not request.apiKey.startswith("sk-"):
            raise HTTPException(status_code=400, detail="Invalid API Key")
        
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""다음 사업계획서를 N2B(NOT-BUT-BECAUSE) 프레임워크로 분석해주세요.

사업계획서:
{request.proposalText}

반드시 아래 JSON 형식으로만 답변하세요. 다른 텍스트 없이 JSON만 출력하세요:
{{"N": "현재의 문제점", "B": "제안하는 솔루션", "C": "근거 및 기대효과", "keywords": ["키워드1", "키워드2", "키워드3"]}}
"""
            }]
        )
        
        text = message.content[0].text.strip()
        
        # JSON 추출
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        # JSON 파싱 시도
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # JSON 파싱 실패시 기본값 반환
            result = {
                "N": "분석 중 오류가 발생했습니다",
                "B": "다시 시도해주세요",
                "C": "입력 내용을 확인해주세요",
                "keywords": ["오류"],
                "raw": text[:500]
            }
        
        return result
        
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key가 유효하지 않습니다")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="API 호출 한도 초과")
    except Exception as e:
        print(f"Error in /analyze: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/match")
async def match(request: MatchRequest):
    try:
        if not request.apiKey or not request.apiKey.startswith("sk-"):
            raise HTTPException(status_code=400, detail="Invalid API Key")
        
        client = anthropic.Anthropic(api_key=request.apiKey)
        n2b = request.n2bAnalysis
        region = request.region if request.region != "전체" else ""
        region_filter = f"{region}" if region else "전국"
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search"
            }],
            messages=[{
                "role": "user",
                "content": f"""다음 N2B 분석 결과와 매칭되는 현재 모집중인 정부지원사업을 검색해주세요.

N2B 분석:
- N (문제점): {n2b.get('N', '')}
- B (솔루션): {n2b.get('B', '')}
- C (근거): {n2b.get('C', '')}
- 키워드: {', '.join(n2b.get('keywords', []))}

지역: {region_filter}

bizinfo.go.kr에서 {region_filter} 지역 현재 모집중인 정부지원사업을 검색하세요.

반드시 아래 JSON 형식으로만 답변하세요:
{{"programs": [{{"name": "사업명", "organization": "주관기관", "region": "지역", "deadline": "마감일", "amount": "지원금액", "url": "링크", "matchScore": 85, "matchReason": "매칭 이유"}}], "searchDate": "오늘날짜"}}
"""
            }]
        )
        
        # 응답에서 텍스트 추출
        result_text = ""
        for block in message.content:
            if hasattr(block, 'text'):
                result_text += block.text
        
        result_text = result_text.strip()
        
        # JSON 추출
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            result = {
                "programs": [],
                "searchDate": "",
                "message": "검색 결과를 파싱하지 못했습니다",
                "raw": result_text[:1000]
            }
        
        result["regionFilter"] = region_filter
        return result
        
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key가 유효하지 않습니다")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="API 호출 한도 초과")
    except Exception as e:
        print(f"Error in /match: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
