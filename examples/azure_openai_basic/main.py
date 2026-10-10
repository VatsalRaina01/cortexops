"""
Azure OpenAI tracing example using CortexOps and LangChain.

Requirements:
    pip install cortexops langchain-openai

Environment Variables:
    AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint URL
    AZURE_OPENAI_API_KEY: Your Azure OpenAI API key
    OPENAI_API_VERSION: Azure OpenAI API version (defaults to 2024-02-15-preview)
    AZURE_OPENAI_DEPLOYMENT_NAME: Name of the deployed model in Azure
    CORTEXOPS_API_KEY: (Optional) Your CortexOps API key
    CORTEXOPS_PROJECT: (Optional) Project name in CortexOps
"""

import os
import sys
from langchain_openai import AzureChatOpenAI
from cortexops import CortexTracer


def main() -> None:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    if not endpoint or not api_key or not deployment_name:
        print("Missing required environment variables.")
        print("Please set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT_NAME.")
        sys.exit(1)

    project_name = os.getenv("CORTEXOPS_PROJECT", "azure-openai-basic")
    tracer = CortexTracer(project=project_name)

    llm = AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=deployment_name,
    )

    traced_llm = tracer.wrap(llm)

    print("Sending prompt to Azure OpenAI via CortexTracer...")
    prompt = "Explain the benefits of AI agent observability in two sentences."
    response = traced_llm.invoke(prompt)

    print("\nAzure OpenAI Response:")
    print(response.content)

    last_trace = tracer.last_trace()
    if last_trace:
        print(f"\nTrace captured: {last_trace.trace_id}")
        print(f"Status: {last_trace.status}")


if __name__ == "__main__":
    main()
