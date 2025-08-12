# the main part

from fastapi import FastAPI
from pydantic import BaseModel
from urllib.parse import urlparse, parse_qs
import json
import logging
import sys
import re
import models

app = FastAPI()

# Select LLM 
llm_provider = models.LLMProvider.ANTHROPIC
llm_client = models.LLMClient(llm_provider)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("uvicorn")

class URLInput(BaseModel):
    url: str

def load_api_data():
    with open("output.json", "r") as f:
        return json.load(f)


def generate_error_json_with_llm(input_url: str, input_params: dict, api_doc: str, reason: str):
    if reason == "param_mismatch":
        prompt = f"""
            Only return a valid JSON error object. No explanation, no extra formatting.

            The user hit a known API endpoint but passed unmatched parameters:
            URL: {input_url}
            Params: {json.dumps(input_params)}

            API spec:
            {api_doc}

            Respond with:
            {{
            "error_code": "invalid_parameters",
            "error_message": "The input parameters do not match any known valid patterns.",
            "error_details": {{
                "received": {json.dumps(input_params)},
                "hint": "Expected keys matching known entries."
            }}
            }}
            """
    elif reason == "url_not_found":
        prompt = f"""
            Only return a valid JSON error object. No explanation, no extra formatting.

            The user called an unknown API URL:
            {input_url}

            Known API list:
            {api_doc}

            Respond with:
            {{
            "error_code": "endpoint_not_found",
            "error_message": "The requested API endpoint does not exist.",
            "error_details": {{
                "suggestion": "Check if the endpoint is misspelled or refer to documentation."
            }}
            }}
            """

    try:
        raw_response = llm_client.generate_content(prompt)
        logger.info(f"Raw LLM response: {raw_response}")

        # Try strict JSON parsing
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw_response.strip(), flags=re.IGNORECASE).strip()

        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode failed: {e}")
        return {
            "error_code": "llm_generation_failed",
            "error_message": "Could not generate LLM-based error response.",
            "error_details": {
                "exception": str(e),
                "raw_response": raw_response  # Add raw Gemini text for debugging
            }
        }

@app.post("/api")
async def match_api(input_data: URLInput):
    input_url = input_data.url
    # print(input_url)
    parsed_input = urlparse(input_url)
    input_base_url = f"{parsed_input.scheme}://{parsed_input.netloc}{parsed_input.path}"
    input_params = {k: v[0] for k, v in parse_qs(parsed_input.query, keep_blank_values=True).items()}

    logger.info(f"Input Base URL: {input_base_url}")
    logger.info(f"Input Params: {input_params}")


    apis = load_api_data()
    api_doc_json = json.dumps(apis, indent=2)

    for api in apis:
        parsed_api_url = urlparse(api["api_url"])
        logger.info(f"Parsed API URL: {parsed_api_url}")
        logger.info(f"API URL: {api['api_url']}")

        logger.info(f"input_url: {input_url}")

        # if(ap)
        api_base_url = f"{parsed_api_url.scheme}://{parsed_api_url.netloc}{parsed_api_url.path}"

        logger.info(f"API Base URL: {api_base_url}")
        logger.info(f"input_base_url: {input_base_url}")

        if input_base_url == api_base_url:
            # URL matched
            logger.info(f"Matching API found: {api['api_url']}")
            success_entry = api["success_response"]["entry"]
            error_entry = api["error_response"]["entry"]
            logger.info(f"Success entry: {success_entry}")
            logger.info(f"Error entry: {error_entry}")
            logger.info(f"Input params: {input_params}")

            # if input_params.keys() in success_entry.keys():
            # if set(input_params.keys()).issubset(success_entry.keys()):
            if input_params == success_entry:
                logger.info(f"Success entry matched: {success_entry}")
                return api["success_response"]
            elif input_params == error_entry:
                logger.info(f"Error entry matched: {error_entry}")
                return api["error_response"]
            else:
                logger.info("Parameters did not match success or error entry.")
                return generate_error_json_with_llm(input_url, input_params, api_doc_json, reason="param_mismatch")

    # No matching base URL found
    return generate_error_json_with_llm(input_url, input_params, api_doc_json, reason="url_not_found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
    # uvicorn main:app --reload --port 8001
