<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>슬기로운 기업경영 v1.0 (데모)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .gradient-bg { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }
        .card-hover:hover { transform: translateY(-3px); box-shadow: 0 15px 40px rgba(255,107,53,0.2); }
        .worry-btn { transition: all 0.3s; }
        .worry-btn:hover { transform: scale(1.02); }
        .worry-btn.selected { ring: 4px; ring-color: #ff6b35; }
    </style>
</head>
<body class="gradient-bg min-h-screen">
    <!-- 헤더 -->
    <header class="text-white py-8">
        <div class="container mx-auto px-4 text-center">
            <h1 class="text-3xl font-bold mb-2">🚀 슬기로운 기업경영</h1>
            <p class="text-gray-300">N2B 기반 AI 경영 파트너 - 정책자금 4대 영역 매칭</p>
            <p class="text-sm text-gray-400 mt-1">v1.0 - 정부지원사업 매칭</p>
            <span class="inline-block mt-3 px-4 py-2 bg-green-500/30 text-green-300 rounded-full text-sm">🎯 데모 모드 - API 키 불필요</span>
        </div>
    </header>

    <main class="container mx-auto px-4 py-6 max-w-2xl">
        <!-- 남은 요청 횟수 -->
        <div class="bg-yellow-500/20 border border-yellow-500/30 rounded-xl p-4 mb-6">
            <p class="text-yellow-200 text-sm">⏳ 남은 데모 요청: <strong id="remainingCount">확인 중...</strong>회 (일일 한도)</p>
        </div>

        <!-- 지역 선택 -->
        <div class="bg-white/10 backdrop-blur rounded-xl p-4 mb-6">
            <label class="block text-sm font-medium text-gray-300 mb-2">📍 지역 선택</label>
            <select id="regionSelect" class="w-full px-4 py-3 bg-white/20 border border-white/30 rounded-lg text-white">
                <option value="전체" class="text-gray-800">🇰🇷 전체 (전국)</option>
                <option value="서울" class="text-gray-800">서울특별시</option>
                <option value="부산" class="text-gray-800">부산광역시</option>
                <option value="대구" class="text-gray-800">대구광역시</option>
                <option value="인천" class="text-gray-800">인천광역시</option>
                <option value="광주" class="text-gray-800">광주광역시</option>
                <option value="대전" class="text-gray-800">대전광역시</option>
                <option value="울산" class="text-gray-800">울산광역시</option>
                <option value="세종" class="text-gray-800">세종특별자치시</option>
                <option value="경기" class="text-gray-800">경기도</option>
                <option value="강원" class="text-gray-800">강원특별자치도</option>
                <option value="충북" class="text-gray-800">충청북도</option>
                <option value="충남" class="text-gray-800">충청남도</option>
                <option value="전북" class="text-gray-800">전북특별자치도</option>
                <option value="전남" class="text-gray-800">전라남도</option>
                <option value="경북" class="text-gray-800">경상북도</option>
                <option value="경남" class="text-gray-800">경상남도</option>
                <option value="제주" class="text-gray-800">제주특별자치도</option>
            </select>
        </div>

        <!-- 5개 문 (고민 선택) -->
        <div class="bg-white/10 backdrop-blur rounded-xl p-6 mb-6">
            <h2 class="text-xl font-bold text-white mb-2">💬 어떤 고민이 있으세요?</h2>
            <p class="text-gray-400 text-sm mb-4">하나를 선택하거나 직접 입력하세요</p>
            
            <div class="space-y-3 mb-4">
                <button onclick="selectWorry('자금이 부족해요. 운영자금, 투자, 대출 등 자금 조달이 필요합니다.')" 
                    class="worry-btn w-full text-left px-4 py-4 bg-gradient-to-r from-yellow-500/20 to-orange-500/20 border border-yellow-500/30 rounded-xl text-white hover:border-yellow-400" id="btn-money">
                    <span class="text-2xl mr-3">💰</span>
                    <span class="font-medium">자금이 부족해요</span>
                    <span class="text-gray-400 text-sm ml-2">정책자금, 융자, 투자</span>
                </button>
                
                <button onclick="selectWorry('직원 관리가 어려워요. 채용, 이직, 인건비, 노무 문제로 고민입니다.')" 
                    class="worry-btn w-full text-left px-4 py-4 bg-gradient-to-r from-blue-500/20 to-cyan-500/20 border border-blue-500/30 rounded-xl text-white hover:border-blue-400" id="btn-people">
                    <span class="text-2xl mr-3">👥</span>
                    <span class="font-medium">직원 관리가 어려워요</span>
                    <span class="text-gray-400 text-sm ml-2">채용, 고용지원금</span>
                </button>
                
                <button onclick="selectWorry('매출이 안 늘어요. 신규 고객 확보, 마케팅, 해외 진출이 필요합니다.')" 
                    class="worry-btn w-full text-left px-4 py-4 bg-gradient-to-r from-green-500/20 to-emerald-500/20 border border-green-500/30 rounded-xl text-white hover:border-green-400" id="btn-growth">
                    <span class="text-2xl mr-3">📈</span>
                    <span class="font-medium">매출이 안 늘어요</span>
                    <span class="text-gray-400 text-sm ml-2">마케팅, 수출, 판로</span>
                </button>
                
                <button onclick="selectWorry('기술개발이 필요해요. R&D, 스마트공장, 신제품 개발을 하고 싶습니다.')" 
                    class="worry-btn w-full text-left px-4 py-4 bg-gradient-to-r from-purple-500/20 to-indigo-500/20 border border-purple-500/30 rounded-xl text-white hover:border-purple-400" id="btn-tech">
                    <span class="text-2xl mr-3">🔬</span>
                    <span class="font-medium">기술개발이 필요해요</span>
                    <span class="text-gray-400 text-sm ml-2">R&D, 스마트공장</span>
                </button>
            </div>
            
            <div class="border-t border-white/20 pt-4">
                <label class="block text-sm text-gray-400 mb-2">또는 직접 입력:</label>
                <textarea id="customWorry" rows="3" class="w-full px-4 py-3 bg-white/20 border border-white/30 rounded-lg text-white placeholder-gray-400" placeholder="구체적인 고민을 적어주세요..."></textarea>
            </div>
        </div>

        <!-- 분석 버튼 -->
        <button onclick="analyzeWorry()" class="w-full py-4 bg-gradient-to-r from-orange-500 to-red-500 text-white rounded-xl font-bold text-lg mb-6 hover:opacity-90 transition">
            🔍 N2B 분석 시작
        </button>

        <!-- 로딩 -->
        <div id="loading" class="hidden text-center py-8">
            <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-orange-500 border-t-transparent"></div>
            <p class="mt-4 text-gray-300" id="loadingText">분석 중...</p>
        </div>

        <!-- N2B 결과 -->
        <div id="n2bResult" class="hidden bg-white rounded-xl shadow-2xl p-6 mb-6">
            <h2 class="text-xl font-bold text-gray-800 mb-4">📊 N2B 분석 결과</h2>
            <div class="space-y-4">
                <div class="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg">
                    <h3 class="font-bold text-red-700">N (Not) - 핵심 문제</h3>
                    <p id="resultN" class="text-gray-700 mt-1"></p>
                </div>
                <div class="bg-blue-50 border-l-4 border-blue-500 p-4 rounded-r-lg">
                    <h3 class="font-bold text-blue-700">B (But) - 해결 방안</h3>
                    <p id="resultB" class="text-gray-700 mt-1"></p>
                </div>
                <div class="bg-green-50 border-l-4 border-green-500 p-4 rounded-r-lg">
                    <h3 class="font-bold text-green-700">B (Because) - 근거</h3>
                    <p id="resultC" class="text-gray-700 mt-1"></p>
                </div>
                <div class="bg-purple-50 p-4 rounded-lg">
                    <h3 class="font-bold text-purple-700 mb-2">🏷️ 키워드</h3>
                    <div id="resultKeywords" class="flex flex-wrap gap-2"></div>
                </div>
            </div>
        </div>

        <!-- 정책 매칭 버튼 -->
        <button onclick="matchPrograms()" id="matchBtn" disabled class="hidden w-full py-4 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-xl font-bold text-lg mb-6 hover:opacity-90 transition disabled:opacity-50">
            🎯 맞춤 정부지원사업 찾기
        </button>

        <!-- 매칭 결과 -->
        <div id="matchResult" class="hidden">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-xl font-bold text-white">🏛️ 추천 정부지원사업</h2>
                <div class="flex gap-2">
                    <span id="totalCount" class="px-3 py-1 bg-green-500/30 text-green-300 rounded-full text-sm"></span>
                    <span id="regionBadge" class="px-3 py-1 bg-purple-500/30 text-purple-300 rounded-full text-sm"></span>
                </div>
            </div>
            <div id="programList" class="space-y-4 mb-6"></div>
            
            <!-- 예상 공고 -->
            <div id="expectedSection" class="hidden">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-xl font-bold text-white">🔮 2026년 예상 공고</h2>
                    <span class="px-3 py-1 bg-orange-500/30 text-orange-300 rounded-full text-sm">미리 준비!</span>
                </div>
                <div id="expectedList" class="space-y-4"></div>
            </div>
        </div>

        <!-- 다음 단계 안내 -->
        <div id="nextStep" class="hidden bg-gradient-to-r from-orange-500/20 to-red-500/20 border border-orange-500/30 rounded-xl p-6 mt-6">
            <h3 class="text-lg font-bold text-white mb-2">📝 다음 단계</h3>
            <p class="text-gray-300 mb-4">원하는 사업을 선택하셨나요? 제안서 작성을 도와드릴 수 있어요!</p>
            <button onclick="goToProposal()" class="px-6 py-3 bg-orange-500 text-white rounded-lg font-medium hover:bg-orange-600 transition">
                제안서 작성하기 →
            </button>
        </div>
    </main>

    <!-- 푸터 -->
    <footer class="text-center py-6 text-gray-500 text-sm">
        <p>© 2024 N2B Framework | Brian Yoo</p>
    </footer>

    <script>
        let n2bAnalysis = null;
        let selectedWorryText = '';
        const API_BASE = 'https://n2b-backend.onrender.com';

        // 초기화 - 남은 요청 횟수 확인
        async function checkDemoStatus() {
            try {
                const response = await fetch(`${API_BASE}/demo/status`);
                const data = await response.json();
                document.getElementById('remainingCount').textContent = data.remaining_requests;
            } catch (error) {
                document.getElementById('remainingCount').textContent = '확인 불가';
            }
        }
        checkDemoStatus();

        function selectWorry(worryText) {
            // 모든 버튼 선택 해제
            document.querySelectorAll('.worry-btn').forEach(btn => {
                btn.classList.remove('ring-4', 'ring-orange-500');
            });
            
            // 선택된 버튼 강조
            event.currentTarget.classList.add('ring-4', 'ring-orange-500');
            
            // 텍스트 저장 및 textarea에 표시
            selectedWorryText = worryText;
            document.getElementById('customWorry').value = worryText;
        }

        async function analyzeWorry() {
            const worryText = document.getElementById('customWorry').value || selectedWorryText;

            if (!worryText) { alert('고민을 선택하거나 입력해주세요.'); return; }

            showLoading(true, '🔍 N2B 분석 중...');

            try {
                const response = await fetch(`${API_BASE}/demo/analyze`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        proposalText: `기업 대표의 고민: ${worryText}\n\n이 고민을 분석하고 정부지원사업과 연결해주세요.` 
                    })
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || '분석 실패');
                }

                // 남은 요청 횟수 업데이트
                if (data.remaining_requests !== undefined) {
                    document.getElementById('remainingCount').textContent = data.remaining_requests;
                }

                // 결과 파싱
                let parsed = {};
                if (data.result) {
                    try {
                        const jsonMatch = data.result.match(/\{[\s\S]*\}/);
                        if (jsonMatch) {
                            parsed = JSON.parse(jsonMatch[0]);
                        }
                    } catch (e) {
                        console.log('Parse error:', e);
                    }
                }

                n2bAnalysis = {
                    not: parsed.not || '분석 결과 없음',
                    but: parsed.but || '분석 결과 없음',
                    because: parsed.because || '분석 결과 없음',
                    keywords: parsed.keywords || []
                };

                document.getElementById('resultN').textContent = n2bAnalysis.not;
                document.getElementById('resultB').textContent = n2bAnalysis.but;
                document.getElementById('resultC').textContent = n2bAnalysis.because;

                const keywordsDiv = document.getElementById('resultKeywords');
                if (n2bAnalysis.keywords.length > 0) {
                    keywordsDiv.innerHTML = n2bAnalysis.keywords.map(k => 
                        `<span class="px-3 py-1 bg-purple-200 text-purple-800 rounded-full text-sm">${k}</span>`
                    ).join('');
                } else {
                    keywordsDiv.innerHTML = '<span class="text-gray-500 text-sm">키워드 없음</span>';
                }

                document.getElementById('n2bResult').classList.remove('hidden');
                document.getElementById('matchBtn').classList.remove('hidden');
                document.getElementById('matchBtn').disabled = false;

            } catch (error) {
                alert('분석 중 오류가 발생했습니다: ' + error.message);
            } finally {
                showLoading(false);
            }
        }

        async function matchPrograms() {
            const region = document.getElementById('regionSelect').value;

            if (!n2bAnalysis) { alert('먼저 N2B 분석을 수행해주세요.'); return; }

            showLoading(true, '🔄 정부지원사업 검색 중...');

            try {
                const response = await fetch(`${API_BASE}/demo/match`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        n2bAnalysis,
                        region
                    })
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || '매칭 실패');
                }

                // 남은 요청 횟수 업데이트
                if (data.remaining_requests !== undefined) {
                    document.getElementById('remainingCount').textContent = data.remaining_requests;
                }

                // 지역 배지
                const regionText = region === '전체' ? '전국' : `전국 + ${region}`;
                document.getElementById('regionBadge').textContent = `📍 ${regionText}`;
                document.getElementById('totalCount').textContent = `📊 ${data.total_programs || 0}개 검색`;

                // 현재 모집중 파싱
                const listDiv = document.getElementById('programList');
                let programs = [];
                if (data.result) {
                    try {
                        const jsonMatch = data.result.match(/\[[\s\S]*\]/);
                        if (jsonMatch) {
                            programs = JSON.parse(jsonMatch[0]);
                        }
                    } catch (e) {
                        console.log('Parse error:', e);
                    }
                }
                
                if (programs.length > 0) {
                    listDiv.innerHTML = programs.map(p => `
                        <div class="bg-white rounded-xl p-4 card-hover transition">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="px-2 py-1 bg-green-100 text-green-700 rounded text-xs">모집중</span>
                                <span class="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">${p.agency || '정부'}</span>
                                <span class="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs">매칭 ${p.fit_score || 85}%</span>
                            </div>
                            <h3 class="font-bold text-gray-800">${p.name || '사업명 없음'}</h3>
                            <p class="text-gray-600 text-sm mt-1">📅 ${p.period || '기간 미정'}</p>
                            <p class="text-purple-600 text-sm mt-2">💡 ${p.reason || ''}</p>
                            ${p.url && p.url !== '' ? `<a href="${p.url}" target="_blank" class="inline-block mt-3 px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 transition">상세보기 →</a>` : ''}
                        </div>
                    `).join('');
                } else {
                    listDiv.innerHTML = `
                        <div class="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-center">
                            <p class="text-yellow-700">😅 현재 모집중인 적합한 지원사업이 없습니다.</p>
                            <p class="text-gray-600 text-sm mt-2">12월은 비수기입니다. 아래 예상 공고를 확인하세요!</p>
                        </div>
                    `;
                }

                // 예상 공고
                const expectedSection = document.getElementById('expectedSection');
                const expectedList = document.getElementById('expectedList');
                const expectedPrograms = data.expected_programs || [];
                
                if (expectedPrograms.length > 0) {
                    expectedSection.classList.remove('hidden');
                    expectedList.innerHTML = expectedPrograms.map(p => `
                        <div class="bg-white/10 backdrop-blur rounded-xl p-4 border border-orange-500/30">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="px-2 py-1 bg-orange-500/30 text-orange-300 rounded text-xs">🔮 ${p.expected_month}</span>
                                <span class="px-2 py-1 bg-blue-500/30 text-blue-300 rounded text-xs">${p.agency || ''}</span>
                                <span class="px-2 py-1 bg-purple-500/30 text-purple-300 rounded text-xs">예상 ${p.match_score || 80}%</span>
                            </div>
                            <h3 class="font-bold text-white">${p.name}</h3>
                            <p class="text-orange-300 text-sm mt-2">⏰ ${p.expected_month} 공고 예상</p>
                        </div>
                    `).join('');
                } else {
                    expectedSection.classList.add('hidden');
                }

                document.getElementById('matchResult').classList.remove('hidden');
                document.getElementById('nextStep').classList.remove('hidden');

            } catch (error) {
                alert('매칭 중 오류가 발생했습니다: ' + error.message);
            } finally {
                showLoading(false);
            }
        }

        function selectProgram(name) {
            alert(`"${name}" 선택!\n\n제안서 작성 기능은 곧 연결됩니다.`);
        }

        function goToProposal() {
            // 제안서 데모 앱으로 이동
            window.location.href = '제안서_생성_데모_v3.html';
        }

        function showLoading(show, text = '분석 중...') {
            document.getElementById('loading').classList.toggle('hidden', !show);
            document.getElementById('loadingText').textContent = text;
        }
    </script>
</body>
</html>
