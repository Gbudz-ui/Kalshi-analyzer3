"""
Netlify Serverless Function - Run Kalshi Analysis
Endpoint: /.netlify/functions/analyze
"""

import json
import os
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
    import anthropic
except ImportError as e:
    def handler(event, context):
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Missing dependency: {str(e)}. Check requirements.txt'})
        }
    # Exit early if imports fail
    import sys
    sys.exit(0)


def handler(event, context):
    """
    Netlify function handler for running Kalshi analysis
    
    Query parameters:
    - max_events: Number of events to analyze (default: 10)
    - min_edge: Minimum edge threshold (default: 0.05)
    """
    
    # CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache'
    }
    
    # Handle OPTIONS request for CORS
    http_method = event.get('httpMethod', 'GET')
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'status': 'ok'})
        }
    
    try:
        # Get environment variables
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
        news_api_key = os.environ.get('NEWS_API_KEY')
        
        if not anthropic_key:
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({'error': 'ANTHROPIC_API_KEY not configured'})
            }
        
        # Parse query parameters
        params = event.get('queryStringParameters', {}) or {}
        max_events = int(params.get('max_events', 10))
        min_edge = float(params.get('min_edge', 0.05))
        
        # Limit to prevent timeout
        max_events = min(max_events, 15)
        
        # Run analysis
        print(f"Starting analysis: max_events={max_events}, min_edge={min_edge}")
        
        analyzer = KalshiAnalyzer(anthropic_key, news_api_key)
        results = analyzer.run_analysis(max_events=max_events)
        
        # Filter by minimum edge
        filtered_results = [r for r in results if abs(r['edge']) >= min_edge]
        
        # Sort by absolute edge
        filtered_results.sort(key=lambda x: abs(x['edge']), reverse=True)
        
        # Prepare response
        response_data = {
            'success': True,
            'generated_at': datetime.now().isoformat(),
            'total_analyzed': len(results),
            'total_opportunities': len(filtered_results),
            'results': filtered_results
        }
        
        print(f"Analysis complete: {len(filtered_results)} opportunities found")
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(response_data, ensure_ascii=False)
        }
        
    except KeyError as e:
        print(f"Configuration error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': f'Configuration error: {str(e)}',
                'message': 'Check that all required environment variables are set'
            })
        }
    except requests.exceptions.RequestException as e:
        print(f"Network error: {str(e)}")
        return {
            'statusCode': 503,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Network error',
                'message': 'Unable to connect to external services. Please try again.'
            })
        }
        
    except Exception as e:
        print(f"Unexpected error in analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'type': type(e).__name__,
                'message': 'An unexpected error occurred. Check function logs for details.'
            })
        }


class KalshiAnalyzer:
    """Simplified analyzer for serverless environment"""
    
    def __init__(self, anthropic_api_key, news_api_key=None):
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.news_api_key = news_api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_active_markets(self):
        """Fetch active Kalshi markets"""
        try:
            response = self.session.get(
                "https://api.elections.kalshi.com/trade-api/v2/markets",
                params={'status': 'open', 'limit': 50},
                timeout=15
            )
            if response.status_code == 200:
                return response.json().get('markets', [])
        except Exception as e:
            print(f"Error fetching markets: {e}")
        return []
    
    def search_news(self, query):
        """Search news sources"""
        sources = []
        
        # Try NewsAPI if available
        if self.news_api_key:
            try:
                response = requests.get(
                    'https://newsapi.org/v2/everything',
                    params={
                        'q': query,
                        'sortBy': 'relevancy',
                        'language': 'en',
                        'pageSize': 5,
                        'apiKey': self.news_api_key
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    articles = response.json().get('articles', [])
                    for article in articles[:5]:
                        sources.append({
                            'title': article.get('title', ''),
                            'description': article.get('description', ''),
                            'url': article.get('url', ''),
                            'source': article.get('source', {}).get('name', 'Unknown')
                        })
            except Exception as e:
                print(f"NewsAPI error: {e}")
        
        # Fallback to Google News RSS
        if not sources:
            try:
                url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US"
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    items = soup.find_all('item')[:5]
                    for item in items:
                        sources.append({
                            'title': item.find('title').text if item.find('title') else '',
                            'url': item.find('link').text if item.find('link') else '',
                            'source': 'Google News',
                            'description': ''
                        })
            except Exception as e:
                print(f"Google News error: {e}")
        
        return sources
    
    def analyze_event(self, event, sources):
        """Analyze event using Claude"""
        
        context = f"""Event: {event.get('title', 'N/A')}
Ticker: {event.get('ticker', 'N/A')}
Current Market Price: {event.get('yes_bid', 50)}%

Recent Sources:
"""
        for i, source in enumerate(sources[:5], 1):
            context += f"{i}. [{source.get('source', 'Unknown')}] {source.get('title', '')}\n"
        
        prompt = f"""{context}

Analyze this prediction market and provide your estimate in JSON:
{{
    "estimated_probability": <0-1>,
    "confidence": "LOW|MEDIUM|HIGH",
    "reasoning": "<brief explanation>"
}}

RESPOND ONLY WITH VALID JSON."""

        try:
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            response_text = response_text.replace('```json\n', '').replace('```', '').strip()
            return json.loads(response_text)
        except Exception as e:
            print(f"Analysis error: {e}")
            return {
                "estimated_probability": 0.5,
                "confidence": "LOW",
                "reasoning": f"Error: {str(e)}"
            }
    
    def run_analysis(self, max_events=10):
        """Run analysis on markets"""
        markets = self.get_active_markets()[:max_events]
        results = []
        
        for market in markets:
            print(f"Analyzing: {market.get('title', '')[:50]}")
            
            query = f"{market.get('title', '')} {market.get('subtitle', '')}"
            sources = self.search_news(query)
            
            analysis = self.analyze_event(market, sources)
            
            market_price = market.get('yes_bid', 50) / 100.0
            estimated_prob = analysis.get('estimated_probability', 0.5)
            edge = estimated_prob - market_price
            
            # Determine recommendation
            confidence = analysis.get('confidence', 'LOW')
            if confidence == 'HIGH' and edge > 0.10:
                rec = 'STRONG_BUY'
            elif confidence == 'HIGH' and edge > 0.05:
                rec = 'BUY'
            elif confidence == 'HIGH' and edge < -0.10:
                rec = 'STRONG_SELL'
            elif edge > 0.15:
                rec = 'BUY'
            elif edge < -0.15:
                rec = 'SELL'
            else:
                rec = 'HOLD'
            
            results.append({
                'ticker': market.get('ticker', 'N/A'),
                'title': market.get('title', 'N/A'),
                'market_price': market_price,
                'estimated_probability': estimated_prob,
                'edge': edge,
                'edge_percent': f"{edge*100:+.1f}%",
                'confidence': confidence,
                'recommendation': rec,
                'reasoning': analysis.get('reasoning', ''),
                'sources_count': len(sources)
            })
        
        return results


# For local testing
if __name__ == "__main__":
    test_event = {
        'httpMethod': 'GET',
        'queryStringParameters': {
            'max_events': '5'
        }
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2))
