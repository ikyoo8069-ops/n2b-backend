from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

class AnalyzeRequest(BaseModel):
    apiKey: str
    proposalText: str

class MatchRequest(BaseModel):
    apiKey: str
    n2bAnalysis: dict

@app.get("/")
async def root():
    return {"message": "N2B API Server is running", "version": "2.0.0 - 실시간 웹검색"}

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
        
        # 1단계: 웹검색으로 현재 모집중인 정부지원사업 찾기
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

bizinfo.go.kr 또는 k-startup.go.kr에서 현재 모집중인 관련 정부지원사업을 검색해주세요.
검색어 예시: "2025년 {n2b.get('keywords', ['중소기업'])[0]} 정부지원사업 모집"

검색 후 다음 JSON 형식으로 답변해주세요:
{{
    "matches": [
        {{
            "title": "사업명",
            "category": "분야 (기술/창업/금융/인력/수출/내수/경영)",
            "agency": "주관기관",
            "deadline": "마감일 (예: 2025-12-31)",
            "url": "상세정보 링크",
            "score": 9,
            "reason": "추천 이유 (2-3문장)"
        }}
    ]
}}

가장 적합한 3개만 추천해주세요. 마감된 사업은 제외하고, 현재 모집중인 사업만 포함해주세요.
"""
            }]
        )
        
        # 응답에서 텍스트 추출
        result_text = ""
        for block in search_message.content:
            if hasattr(block, 'text'):
                result_text += block.text
        
        # JSON 파싱
        result_text = result_text.replace("```json", "").replace("```", "").strip()
        
        # JSON 부분만 추출
        start_idx = result_text.find('{')
        end_idx = result_text.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = result_text[start_idx:end_idx]
            result = json.loads(json_str)
        else:
            # JSON을 찾지 못한 경우 기본 응답
            result = {
                "matches": [
                    {
                        "title": "검색 결과를 처리할 수 없습니다",
                        "category": "기타",
                        "agency": "-",
                        "deadline": "-",
                        "url": "https://www.bizinfo.go.kr",
                        "score": 0,
                        "reason": "다시 시도해주세요."
                    }
                ]
            }
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
