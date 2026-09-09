import {test} from 'node:test';
import assert from 'node:assert/strict';
import {splitThinking, displayParts} from '../src/thinking.ts';

test('separates thinking and answer, preserving order and multiple blocks', () => {
  assert.deepEqual(splitThinking('before<think>reason</think>answer<think>more</think>end'), [
    {type:'text',text:'before'}, {type:'reasoning',text:'reason'},
    {type:'text',text:'answer'}, {type:'reasoning',text:'more'}, {type:'text',text:'end'},
  ]);
});
test('every stream prefix keeps reasoning out of the answer and hides partial tags', () => {
  const text = '<think>private reasoning</think>final answer';
  for (let i = 1; i <= text.length; i++) {
    const parts = splitThinking(text.slice(0,i), true);
    const answer = parts.filter(p=>p.type==='text').map(p=>p.text).join('');
    assert.equal(answer, i <= 32 ? '' : text.slice(32,i));
    assert.ok(parts.every(p=>!p.text.includes('<') && !p.text.includes('>')));
  }
});
test('unclosed historical thinking stays separate and final literal prefixes are preserved', () => {
  assert.deepEqual(splitThinking('<think>unfinished'), [{type:'reasoning',text:'unfinished'}]);
  assert.deepEqual(splitThinking('answer <thi'), [{type:'text',text:'answer <thi'}]);
});
test('code samples and escaped tags are not interpreted as reasoning', () => {
  for (const text of ['`<think>example</think>`', '```xml\n<think>example</think>\n```', '~~~html\n<think>example</think>\n~~~', '\\<think>example']) {
    assert.deepEqual(splitThinking(text), [{type:'text',text}]);
  }
});
test('adjacent text parts support split tags, native reasoning and tools retain order', () => {
  const parts = displayParts([
    {id:'a',type:'text',text:'<thi'}, {id:'b',type:'text',text:'nk>reason</think>answer'},
    {id:'c',type:'tool'}, {id:'d',type:'reasoning',text:'native'},
  ], true);
  assert.deepEqual(parts.map(p=>[p.type,p.text]), [['reasoning','reason'],['text','answer'],['tool',undefined],['reasoning','native']]);
  const user = [{type:'text',text:'<think>literal user input</think>'}];
  assert.equal(displayParts(user,false),user);
});
