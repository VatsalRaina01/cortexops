# Azure OpenAI Basic Example

This example shows how to use CortexOps tracing with Azure OpenAI models using LangChain's `AzureChatOpenAI` wrapper.

## Setup

Make sure you have installed the required dependencies:

```bash
pip install cortexops langchain-openai
```

Set your environment variables in your terminal or in a `.env` file:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource-name.openai.azure.com/"
export AZURE_OPENAI_API_KEY="your-azure-api-key"
export OPENAI_API_VERSION="2024-02-15-preview"
export AZURE_OPENAI_DEPLOYMENT_NAME="your-deployment-name"
```

## Running the Example

Run the python script to trigger a traced call:

```bash
python main.py
```
