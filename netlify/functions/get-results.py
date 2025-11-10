"""
Netlify Serverless Function - Get Latest Results
Endpoint: /.netlify/functions/get-results
"""

import json
import os


def handler(event, context):
    """
    Netlify function handler for retrieving latest analysis results
    Returns a sample result structure for demo purposes
    """
    
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache'
    }
    
    http_method = event.get('httpMethod', 'GET')
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'status': 'ok'})
        }
    
    try:
        # Return instructions for first-time users
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'message': 'No cached results available yet. Click "Run New Analysis" to generate results.',
                'instructions': 'Use the "Run New Analysis" button to analyze current Kalshi markets.',
                'results': [],
                'total_analyzed': 0,
                'total_opportunities': 0
            })
        }
        
    except Exception as e:
        print(f"Error in get-results: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'message': 'Error retrieving results'
            })
        }
