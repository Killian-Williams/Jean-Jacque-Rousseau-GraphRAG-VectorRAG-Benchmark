from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
import json
from unittest.mock import patch
from budget_gateway import Ledger, reservation, usage_cost


class BudgetTests(unittest.TestCase):
    def test_concurrent_reservations_cannot_exceed_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp)/'cost.json', '0.10')
            row = ledger.reserve(Decimal('0.06'), 'model', '/v1/chat/completions')
            with self.assertRaises(ValueError):
                ledger.reserve(Decimal('0.05'), 'model', '/v1/chat/completions')
            self.assertEqual(len(ledger.records), 1)
            ledger.settle(row, 599)
            self.assertEqual(row['accounted_usd'], '0.06')

    def test_settlement_and_error_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp)/'cost.json')
            row = ledger.reserve(Decimal('0.10'), 'gpt-4.1-mini', '/v1/chat/completions')
            ledger.settle(row, 200, {'prompt_tokens': 1000, 'completion_tokens': 100})
            self.assertEqual(Decimal(row['accounted_usd']), Decimal('0.00056'))
            row = ledger.reserve(Decimal('0.10'), 'gpt-4.1-mini', '/v1/chat/completions')
            ledger.settle(row, 401)
            self.assertEqual(row['accounted_usd'], '0')

    def test_unpriced_requests_rejected(self):
        for path, payload in [('/v1/responses', {'model':'gpt-4.1-mini','previous_response_id':'hidden'}),
                              ('/v1/chat/completions', {'model':'gpt-5'}),
                              ('/v1/chat/completions', {'model':'gpt-4.1-mini','n':2})]:
            with self.assertRaises(ValueError):
                reservation(path, payload)

    def test_maximum_output_reserved(self):
        amount = reservation('/v1/chat/completions', {'model':'gpt-4.1-mini','messages':[]})
        self.assertGreater(amount, Decimal('0.0524288'))

    def test_transient_windows_replace_failure_is_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path.replace
            attempts = []
            def replace(source, target):
                attempts.append(1)
                if len(attempts) == 1:
                    raise PermissionError('Simulated Windows sharing violation')
                return original(source, target)
            with patch.object(Path, 'replace', replace):
                ledger = Ledger(Path(tmp)/'cost.json')
            self.assertEqual(len(attempts), 2)

    def test_retry_attempt_carries_all_previous_reservations(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior = Ledger(Path(tmp)/'first.json', '0.10')
            prior.reserve(Decimal('0.06'), 'model', '/v1/chat/completions')
            next_ledger = Ledger(Path(tmp)/'second.json', '0.10', prior.path)
            self.assertEqual(next_ledger.records[0]['accounted_usd'], '0.06')
            self.assertEqual(next_ledger.records[0]['state'], 'prior_attempt_maximum_retained')
            with self.assertRaises(ValueError):
                next_ledger.reserve(Decimal('0.05'), 'model', '/v1/chat/completions')

    def test_cached_usage_is_repriced_without_resetting_spend(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior = Path(tmp)/'old.json'
            prior.write_text(json.dumps({'operating_limit_usd':'14.40','requests':[{
                'state':'usage_received','endpoint':'/v1/chat/completions',
                'accounted_usd':'0.00056','usage':{'prompt_tokens':1000,'completion_tokens':100,
                  'prompt_tokens_details':{'cached_tokens':800}}}]}))
            ledger = Ledger(Path(tmp)/'new.json',prior=prior)
            row=ledger.records[0]
            self.assertEqual(Decimal(row['accounted_usd']),Decimal('0.00032'))
            self.assertEqual(row['previous_accounted_usd'],'0.00056')
            with self.assertRaises(ValueError):
                usage_cost('/v1/chat/completions',{'prompt_tokens':100,'prompt_tokens_details':{'cached_tokens':101}})

    def test_responses_accounting_matches_chat(self):
        payload={'model':'gpt-4.1-mini','input':[{'role':'user','content':'Judge these answers'}]}
        self.assertGreater(reservation('/v1/responses',payload),Decimal('0.0524288'))
        usage={'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':800}}
        self.assertEqual(usage_cost('/v1/responses',usage),Decimal('0.00032'))

    def test_explicit_budget_increase_preserves_spending(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior=Ledger(Path(tmp)/'first.json')
            prior.reserve(Decimal('4.16'),'model','/v1/chat/completions')
            next_ledger=Ledger(Path(tmp)/'next.json','19.70',prior.path,authorized='20.00')
            self.assertEqual(next_ledger.records[0]['accounted_usd'],'4.16')
            self.assertEqual(next_ledger.authorized,Decimal('20.00'))


if __name__ == '__main__':
    unittest.main()
