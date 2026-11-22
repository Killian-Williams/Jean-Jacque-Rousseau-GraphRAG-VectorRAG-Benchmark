"""Budget-adaptive paired benchmark; preserves the full original question set."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

from budget_gateway import Ledger, start

ROOT = Path(r'C:\Users\Willi\AppData\Local\RousseauBenchmark\20261122\repository')
BASE = ROOT/'runs/rousseau-20261122-budget1466-r2'
JOB = BASE/'budget-benchmark-20'
CATEGORIES = ('local_fact_retrieval','cross_document_reasoning','global_sensemaking')
SEED = 20261122


def save(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for attempt in range(300):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt==299:raise
            time.sleep(.1)


def schedule(questions):
    rng=random.Random(SEED)
    groups=[]
    for category in CATEGORIES:
        group=[q for q in questions if q['category']==category]
        rng.shuffle(group)
        groups.append(group)
    ordered=[]
    for i in range(max(map(len,groups))):
        for group in groups:
            if i<len(group):ordered.append(group[i])
    if len(ordered)!=len(questions) or len({q['id'] for q in ordered})!=len(ordered):
        raise ValueError('Question schedule is incomplete or contains duplicate IDs')
    return ordered


def cost(ledger):
    with ledger.lock:
        return sum(Decimal(r['accounted_usd']) for r in ledger.records)


def bundle(original, completed, provenance):
    questions=json.loads(json.dumps(original))
    name='Rousseau_Controlled_Budget_Benchmark_20261122'
    questions.update(benchmark_name=name,questions=[x['question'] for x in completed],provenance=provenance)
    questions['description']='Budget-limited subset of the original 60-question benchmark; do not present as the complete original benchmark.'
    questions['design']['total_questions']=len(completed)
    questions['design']['categories']={c:sum(x['question']['category']==c for x in completed) for c in CATEGORIES}
    answers={}
    for system in ('vector_rag','graphrag'):
        answers[system]={'benchmark_name':name,'system':system,'total_completed':len(completed),
                         'results':[x['answers'][system] for x in completed],'provenance':provenance}
        if system=='graphrag':answers[system]['query_method']='global'
    evaluations=[row for x in completed for row in x['evaluations']]
    judges={'benchmark_name':name,'evaluation_method':'pairwise_llm_as_a_judge','judge_model':'gpt-4.1-mini',
            'judge_runs_per_criterion':3,'criteria':['comprehensiveness','diversity','empowerment','directness'],
            'total_evaluations':len(evaluations),'evaluations':evaluations,'provenance':provenance}
    return questions,answers,judges


def main():
    from dotenv import dotenv_values
    sys.path.insert(0,str(ROOT/'scripts'))
    import experiment
    manifest=json.loads((BASE/'run.json').read_text())
    for stage in ('index-vector','index-graph','sample'):
        if manifest['stages'][stage]['status']!='completed':raise ValueError('Unfinished prerequisite: '+stage)
    experiment.verify_snapshot(BASE,manifest)
    env={'python':sys.version,'packages':subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines()}
    if env!=manifest['environment']:raise ValueError('Environment differs from index/sample environment')
    original=json.loads((BASE/'benchmark/questions.json').read_text(encoding='utf-8'))
    ordered=schedule(original['questions'])
    JOB.mkdir(exist_ok=False)
    (JOB/'benchmark').mkdir(); (JOB/'question-checkpoints').mkdir(); (JOB/'execution-code').mkdir()
    ledger=Ledger(JOB/'api-cost-ledger.json',limit='19.70',prior=BASE/'api-cost-ledger.json',authorized='20.00')
    key=dotenv_values(Path(r'C:\Users\Willi\OneDrive\Desktop\Rousseau_GraphRAG\.env'))['GRAPHRAG_API_KEY']
    server,base,token=start(ledger,key,port=urlparse(manifest['run_overrides']['api_base']).port)
    if base!=manifest['run_overrides']['api_base']:raise ValueError('Unexpected gateway endpoint')
    os.environ.update(OPENAI_API_KEY=token,GRAPHRAG_API_KEY=token,OPENAI_BASE_URL=base,OPENAI_API_BASE=base,
                      JUDGE_MODEL='gpt-4.1-mini',JUDGE_RUNS='3',PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')
    sys.path.insert(0,str(BASE/'benchmark'))
    import run_vector_rag as vector
    import run_graphrag as graph
    import evaluate as evaluator
    code={}
    sources=[Path(__file__),Path(__file__).parent/'budget_gateway.py',Path(__file__).parent/'test_budget.py',
             BASE/'benchmark/run_vector_rag.py',BASE/'benchmark/run_graphrag.py',BASE/'benchmark/evaluate.py',BASE/'benchmark/analysis.py']
    for source in sources:
        dest=JOB/'execution-code'/source.name
        shutil.copyfile(source,dest)
        code[source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
    shutil.copyfile(BASE/'benchmark/analysis.py',JOB/'benchmark/analysis.py')
    provenance={'run_id':'rousseau-20261122-budget20-adaptive','base_run_id':manifest['run_id'],
                'corpus_id':manifest['corpus']['corpus_id'],'source_commit':manifest['source_commit'],
                'index_ids':{k:v['id'] for k,v in manifest['indexes'].items()},
                'index_content_ids':{k:v.get('content_id',v['id']) for k,v in manifest['indexes'].items()},
                'original_question_count':len(ordered),'original_questions_sha256':hashlib.sha256((BASE/'benchmark/questions.json').read_bytes()).hexdigest(),
                'code_sha256':code,'sampling_seed':SEED,'selection_method':'Seeded shuffle within each category; round-robin categories; stop based on remaining budget, never judge outcomes.',
                'execution_change':'Generate both answers and all 12 judgments for each question before the next question. Prompts, models, indexes, rubric and three votes per criterion are unchanged. Latencies include instrumented API transport and GraphRAG CLI startup.'}
    state={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'authorization_usd':'20.00',
           'operating_ceiling_usd':'19.70','initial_accounted_usd':str(cost(ledger)),
           'authorization_history':[{'limit_usd':'14.66'},{'limit_usd':'20.00','scope':'Cumulative across earlier indexes, samples, retries and this partial benchmark.'}],
           'schedule':[q['id'] for q in ordered],'completed_ids':[],'provenance':provenance,'environment':env}
    save(JOB/'run.json',state)
    completed=[]; pair_costs=[]; stop_reason='all_questions_completed'
    print('START adaptive benchmark; carried-forward USD',cost(ledger),flush=True)
    try:
        for q in ordered:
            # Reserve room for another query pair and its 12 short judgments.
            # The independent request gate still enforces worst-case output bounds.
            needed=max(pair_costs[-5:] or [Decimal('.34')])*Decimal('1.15')+Decimal('.12')
            if ledger.limit-cost(ledger)<needed:
                stop_reason='insufficient_safe_room_for_another_judged_pair';break
            experiment.verify_snapshot(BASE,manifest)
            before=cost(ledger)
            checkpoint={'question':q,'answers':{},'evaluations':[],'status':'running'}
            checkpoint_file=JOB/'question-checkpoints'/(q['id']+'.json')
            save(checkpoint_file,checkpoint)
            print('QUESTION',q['id'],q['category'],'remaining operating USD',ledger.limit-before,flush=True)
            for system,ask in [('vector_rag',vector.ask_rag),('graphrag',graph.ask_graphrag)]:
                ledger.stage=system+':'+q['id']
                start_time=time.time()
                answer=ask(q['question'])
                elapsed=time.time()-start_time
                if not isinstance(answer,str) or not answer.strip():raise ValueError('Empty answer: '+system)
                result={k:v for k,v in q.items() if k!='id'}
                result.update(question_id=q['id'],system=system,answer=answer,latency_seconds=round(elapsed,3),error=None)
                if system=='graphrag':result['query_method']='global'
                checkpoint['answers'][system]=result
                save(checkpoint_file,checkpoint)
                print('ANSWER',q['id'],system,round(elapsed,2),'seconds',flush=True)
            pair={'question_id':q['id'],'vector_answer':checkpoint['answers']['vector_rag']['answer'],
                  'graphrag_answer':checkpoint['answers']['graphrag']['answer']}
            for criterion in evaluator.CRITERIA:
                for run_number in range(1,4):
                    ordering=evaluator.arrange_answers(pair,criterion,run_number)
                    ledger.stage='judge:'+q['id']
                    judgment,usage=evaluator.judge_answers(q['question'],ordering['answer_1'],ordering['answer_2'],criterion)
                    result={'question_id':q['id'],'category':q['category'],'question':q['question'],
                            'criterion':criterion,'run_number':run_number,'answer_1_system':ordering['answer_1_system'],
                            'answer_2_system':ordering['answer_2_system'],'judge_winner':judgment['winner'],
                            'winner_system':evaluator.get_winner_system(judgment['winner'],ordering),
                            'reasoning':judgment['reasoning'],'judge_model':'gpt-4.1-mini',**usage,'status':'completed','error':None}
                    checkpoint['evaluations'].append(result)
                    save(checkpoint_file,checkpoint)
            checkpoint.update(status='completed',accounted_cost_usd=str(cost(ledger)-before))
            save(checkpoint_file,checkpoint)
            completed.append(checkpoint);pair_costs.append(cost(ledger)-before)
            state['completed_ids'].append(q['id'])
            state['accounted_usd']=str(cost(ledger))
            save(JOB/'run.json',state)
            print('JUDGED',q['id'],'completed',len(completed),'total USD',cost(ledger),flush=True)
    except Exception as exc:
        stop_reason='budget_guard' if ledger.exhausted.is_set() else 'execution_error'
        state['error']=str(exc)
        print('STOP',stop_reason,str(exc),flush=True)
    finally:
        server.shutdown(); server.server_close()
    if completed:
        selected,answers,judges=bundle(original,completed,provenance)
        save(JOB/'benchmark/questions.json',selected)
        save(JOB/'benchmark/vector_answers.json',answers['vector_rag'])
        save(JOB/'benchmark/graphrag_answers.json',answers['graphrag'])
        save(JOB/'benchmark/evaluations.json',judges)
        from check_repository import check_benchmark,check_summaries
        check_benchmark(JOB)
        subprocess.run([sys.executable,'-I','-S',str(JOB/'benchmark/analysis.py')],check=True,stdout=subprocess.DEVNULL)
        check_summaries(JOB)
    state.update(status='finished',stop_reason=stop_reason,completed_questions=len(completed),
                 total_questions=60,accounted_usd=str(cost(ledger)),finished_at=datetime.now(timezone.utc).isoformat(),
                 paid_process_running=False,validation='passed' if completed else 'no complete pairs')
    save(JOB/'run.json',state)
    print('FINISHED',len(completed),'of 60 questions; cumulative USD',cost(ledger),'reason',stop_reason,flush=True)
    return 0 if stop_reason!='execution_error' else 1


if __name__=='__main__':
    sys.exit(main())
