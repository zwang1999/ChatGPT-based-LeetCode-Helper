
import requests
import json
import re
import time

session = requests.Session()
user_agent = r'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36'

def get_question_by_slug_multiprocessing(slug, sleep = False):
    url = 'https://leetcode.com/graphql'
    params = {
        'operationName': 'getQuestionDetail',
        'variables': {'titleSlug': slug},
        'query': '''
            query getQuestionDetail($titleSlug: String!) {
                question(titleSlug: $titleSlug) {
                    questionId
                    similarQuestions
                    difficulty
                    topicTags {name}
                    content
                    codeSnippets {code}
                }
            }
        '''
    }
    params = json.dumps(params).encode('utf8')         
    headers = {
        'User-Agent': user_agent,
        'Connection': 'keep-alive', 
        'Content-Type': 'application/json',
        'Referer': 'https://leetcode.com/problems/' + slug
    }
    response = session.post(url, data = params, headers = headers, timeout = 10)
    content = response.json()
    
    if sleep:
        time.sleep(1)
    
    question = content['data']['question']
    question['similarQuestions'] = parse_similar_questions(question['similarQuestions'])
    question['topicTags'] = [info['name'] for info in question['topicTags']]
    question['content'] = parse_content(question['content'])
    question['code'] = question['codeSnippets'][3]['code'] # python3 starter code
    return question

def parse_similar_questions(s):
    questions = s[2:-2].split('}, {')
    for i, q in enumerate(questions):
        q = q[1:]
        questions[i] = {}
        for info in q.split('", "')[:-1]:
            info = info.split('": "')
            questions[i][info[0]] = info[1]
    return questions

def parse_content(s):
    contents = s.split('Constraints:')
    contents = contents[0].split('<strong class="example">') + ['Constraints: ' + contents[1].split('Follow-up:')[0]]
    replace_before = [
        ('<p>', ' '), ('</p>', ' '), 
        ('<code>', ' '), ('</code>', ' '), 
        ('<em>', ' '), ('</em>', ' '), 
        ('<li>', ' '), ('</li>', ' '), 
        ('<strong>', ' '), ('</strong>', ' '), 
        ('<pre>', ' '), ('</pre>', ' '),
        ('<sup>', '^'), ('</sup>', ' '), 
        ('<sub>', '_'), ('</sub>', ' '), 
        ('<ul>', ' '), ('</ul>', ' '),
        ('&nbsp;', ' '),
        ('&#39;', '\''),
        ('&lt;', '<'),
        ('&quot;', '"'),
        ('\n', ' ')
    ]
    replace_after = [
        (' ,', ','), 
        (' .', '.'), 
        (' ;', ';'),
        ('.;', ';'),
        (' Output:', '; Output:'),
        (' Explanation:', '; Explanation:')
    ]
    contents[-1] = contents[-1].replace('</li>', ';')
    for i in range(len(contents)):
        for s1, s2 in replace_before:
            contents[i] = contents[i].replace(s1, s2)
        contents[i] = re.sub('<.*/>', ' ', contents[i]) # for image
        contents[i] = ' '.join(contents[i].split()) # remove extra whitespace
        for s1, s2 in replace_after:
            contents[i] = contents[i].replace(s1, s2)
    contents[-1] = contents[-1][:-1] + '.'
    return contents
