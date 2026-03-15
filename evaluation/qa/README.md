# QA Generation Pipeline

This tool generates evaluation QA pairs from PubTator3 full-text papers using Anthropic or Google Gemini models.

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   Create a `.env` file in this directory to store your API keys:
   ```env
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   GOOGLE_API_KEY=your_google_api_key_here
   ```

## Usage

Generate QA pairs using the default Anthropic model:
```bash
python generate_qa.py --generate
```

Generate QA pairs using the Google Gemini model:
```bash
python generate_qa.py --generate --provider google
```

Specify a custom model:
```bash
python generate_qa.py --generate --provider google --model gemini-1.5-pro
```
