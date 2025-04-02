import os
import json
import re
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# OpenAI 클라이언트 설정
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class QueryGenerator:
    def __init__(self, schema_info: Dict[str, Any] = None):
        self.schema_info = schema_info
        self.system_prompt = """
        당신은 SQL 전문가입니다. 사용자의 자연어 질문을 바탕으로 적절한 SQL 쿼리를 생성해야 합니다.
        제공된 데이터베이스 스키마 정보를 활용하여 질문에 정확히 대응하는 쿼리를 생성하세요.
        가능한 단순하고 효율적인 쿼리를 작성하세요. 읽기 전용 쿼리만 생성하세요.
        """

    def update_schema(self, schema_info: Dict[str, Any]):
        """스키마 정보 업데이트"""
        self.schema_info = schema_info

    def format_schema_for_prompt(self) -> str:
        """프롬프트용 스키마 정보 포맷팅"""
        if not self.schema_info:
            return "스키마 정보가 없습니다."

        formatted = "데이터베이스 스키마 정보:\\n"
        
        # 테이블 정보 포맷팅
        for table_name, columns in self.schema_info.get("tables", {}).items():
            formatted += f"\\n테이블: {table_name}\\n"
            formatted += "컬럼:\\n"
            for column in columns:
                formatted += f"- {column['name']} ({column['type']})"
                if column['key'] == 'PRI':
                    formatted += " [기본키]"
                elif column['key']:
                    formatted += f" [{column['key']}]"
                formatted += "\\n"

        # 관계 정보 포맷팅
        if self.schema_info.get("relationships"):
            formatted += "\\n관계:\\n"
            for rel in self.schema_info["relationships"]:
                formatted += f"- {rel['table']}.{rel['column']} -> {rel['referenced_table']}.{rel['referenced_column']}\\n"

        return formatted

    async def generate_query(self, question: str, database: str) -> Dict[str, Any]:
        """사용자 질문을 SQL 쿼리로 변환"""
        schema_prompt = self.format_schema_for_prompt()

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"데이터베이스: {database}\\n\\n{schema_prompt}\\n\\n사용자 질문: {question}\\n\\nSQL 쿼리를 생성하되 쿼리만 반환하세요. 설명은 필요없습니다."}
        ]

        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.1,
                max_tokens=500
            )

            query = response.choices[0].message.content.strip()
            # SQL 쿼리에서 불필요한 마크다운 제거
            query = re.sub(r'^```sql\\s*', '', query)
            query = re.sub(r'\\s*```$', '', query)

            return {
                "query": query,
                "database": database,
                "params": {}
            }
        except Exception as e:
            return {
                "error": str(e),
                "query": None
            }

    async def analyze_results(self, question: str, query_result: Dict[str, Any]) -> str:
        """쿼리 결과를 분석하여 자연어 응답 생성"""
        results = query_result.get("results", [])
        count = query_result.get("count", 0)

        if count == 0:
            return "검색 결과가 없습니다."

        # 결과를 문자열로 포맷팅
        formatted_results = json.dumps(results, ensure_ascii=False, indent=2)

        messages = [
            {"role": "system", "content": "당신은 데이터 분석 전문가입니다. SQL 쿼리 결과를 바탕으로 사용자의 질문에 자연어로 답변해야 합니다."},
            {"role": "user", "content": f"사용자 질문: {question}\\n\\n쿼리 결과 (총 {count}개 행):\\n{formatted_results}\\n\\n이 결과를 바탕으로 사용자 질문에 답변해주세요. 전문적이지만 이해하기 쉽게 답변하세요."}
        ]

        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"결과 분석 중 오류가 발생했습니다: {str(e)}"