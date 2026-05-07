# bharat_veto_agent.py
# BHARATEDGE - AI Veto Agent (Groq/Llama3)
# Reviews NSE stock signals before execution

import os
import json
import logging

logger = logging.getLogger(__name__)


class BharatVetoAgent:
    """
    AI-powered trade review for Indian markets.
    Uses Groq/Llama3 to review BUY signals.
    """

    def __init__(self):
        self.api_key = os.getenv('GROQ_API_KEY', '')
        self.enabled = bool(self.api_key)
        self.model   = 'llama-3.3-70b-versatile'

        if not self.enabled:
            print("   Veto Agent: GROQ_API_KEY not found")
        else:
            print("   Veto Agent: Groq/Llama3 connected ✅")

    def review_signal(self,
                      symbol,
                      price,
                      confidence,
                      sector,
                      market_regime,
                      mtf_score,
                      current_positions,
                      india_vix=None):

        if not self.enabled:
            return {
                'decision'  : 'APPROVE',
                'reason'    : 'Veto agent disabled',
                'confidence': 0.5,
            }

        try:
            from groq import Groq
            client = Groq(api_key=self.api_key)

            positions_text = ', '.join(current_positions.keys()) \
                if current_positions else 'None'
            vix_text = f"{india_vix:.1f}" if india_vix else "Unknown"

            prompt = f"""You are a senior risk manager at an Indian hedge fund.
Review this NSE stock trade signal and decide APPROVE or VETO.

TRADE SIGNAL:
Symbol: {symbol}
Price: Rs{price:.2f}
Sector: {sector}
Market Regime: {market_regime}
AI Confidence: {confidence:.3f}
Multi-timeframe Score: {mtf_score:.0%}
India VIX: {vix_text}

PORTFOLIO:
Open Positions: {positions_text}
Count: {len(current_positions)}/5

Respond with ONLY this JSON:
{{
    "decision": "APPROVE" or "VETO",
    "reason": "One sentence",
    "confidence": 0.0 to 1.0
}}

VETO if:
- India VIX above 20 and confidence below 0.65
- Market regime is bearish
- Stock already in portfolio
- Confidence below 0.55

APPROVE if:
- Confidence above 0.65
- Market conditions reasonable
- Good diversification opportunity"""

            response = client.chat.completions.create(
                model    = self.model,
                messages = [
                    {
                        "role"   : "system",
                        "content": "You are a strict Indian market risk manager. Respond only with valid JSON."
                    },
                    {
                        "role"   : "user",
                        "content": prompt
                    }
                ],
                temperature = 0.1,
                max_tokens  = 150,
            )

            response_text = response.choices[0].message.content.strip()

            if '```' in response_text:
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]

            result     = json.loads(response_text)
            decision   = result.get('decision', 'APPROVE').upper()
            reason     = result.get('reason', 'No reason')
            confidence = float(result.get('confidence', 0.5))

            if decision not in ['APPROVE', 'VETO']:
                decision = 'APPROVE'

            print(f"   Veto Agent [{symbol}]: {decision}")
            print(f"   Reason: {reason}")

            return {
                'decision'  : decision,
                'reason'    : reason,
                'confidence': confidence,
            }

        except Exception as e:
            logger.warning(f"Veto agent error for {symbol}: {e}")
            return {
                'decision'  : 'APPROVE',
                'reason'    : f'Error: {e}',
                'confidence': 0.5,
            }


if __name__ == '__main__':
    print("\nTesting BharatEdge Veto Agent...")
    agent = BharatVetoAgent()
    result = agent.review_signal(
        symbol            = 'TCS.NS',
        price             = 3450.00,
        confidence        = 0.72,
        sector            = 'IT',
        market_regime     = 'BULL',
        mtf_score         = 1.0,
        current_positions = {},
        india_vix         = 15.0,
    )
    print(f"\nDecision: {result['decision']}")
    print(f"Reason: {result['reason']}")