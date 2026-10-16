"""Deterministic long history for isolated browser/payload checks; no external calls."""


def seed_history(memory, rounds=45):
    for index in range(rounds):
        run_id = f'history-{index:04d}'
        query = f'历史样本问题 {index:03d}'
        answer = '## 历史阅读样本\n\n' + '这是用于分页与阅读位置验证的隔离文本。' * 100
        answer += '\n```typescript\n' + '\n'.join(f'const value{i} = {i}' for i in range(30)) + '\n```\n证据见 [S1]。'
        result = {'answer': answer, 'sources': ['fixture'], 'source_map': [
            {'citation_id': 'S1', 'source': 'fixture', 'excerpt': f'第 {index} 轮的隔离证据'}]}
        memory.start_run(run_id, 'history-fixture', query, {
            'knowledge_base_id': '', 'search_scope': 'auto', 'model_profile': 'default', 'thinking_mode': ''})
        memory.save_input(run_id, 'history-fixture', query, [])
        if index % 15 == 5:
            memory.finish_run(run_id, 'cancelled', {'answer': '已取消的历史草稿'})
        else:
            memory.complete_run(run_id, result, {'run_id': run_id, 'query': query, 'response': answer,
                                                'timestamp': index + 1, 'result': result})
        for seq in range(8):
            memory.record_event({'run_id': run_id, 'session_id': 'history-fixture', 'seq': seq + 1,
                                 'timestamp': index + 1, 'type': 'info',
                                 'data': {'step': 'fixture', 'summary': {'index': index}}})
