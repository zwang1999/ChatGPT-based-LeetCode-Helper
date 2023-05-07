import requests
import json
import re
import time
from scipy import stats
from queue import Queue
from threading import Thread
from threading import Lock
import openai
import argparse

session = requests.Session()
user_agent = r'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36'

def get_question_info():
    # Only focus on the questions with python solutions ('Algorithm').
    url = 'https://leetcode.com/api/problems/algorithms/'
    headers = {
        'User-Agent': user_agent, 
        'Connection': 'keep-alive'
    }
    response = session.get(url, headers = headers, timeout = 10)
    question_info = []
    question_list = json.loads(response.content.decode('utf-8'))
    for question in question_list['stat_status_pairs']:
        backend_id = question['stat']['question_id']
        frontend_id = question['stat']['frontend_question_id']
        title = question['stat']['question__title']
        slug = question['stat']['question__title_slug']
        difficulty = question['difficulty']['level']
        paid_only = question['paid_only']
        question_info.append((backend_id, frontend_id, title, slug, difficulty, paid_only)) 
    return question_info

def get_question_by_slug(slug, sleep = False):
    url = 'https://leetcode.com/graphql'
    params = {
        'operationName': 'getQuestionDetail',
        'variables': {'titleSlug': slug},
        'query': '''
            query getQuestionDetail($titleSlug: String!) {
                question(titleSlug: $titleSlug) {
                    questionId
                    similarQuestions
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
        time.sleep(0.5)
    
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

def content_to_prompt(content, code, feedback):
    description = 'Here is the question prompt:\n'
    description += content[0] + '\n'
    
    examples = 'Here are the example cases of input/output to better understand the question:\n'
    for example in content[1:-1]:
        examples += example + '\n'
    
    constraints = 'Here are the constraints on the value of variables:\n'
    constraints += content[-1] + '\n'
    
    starter_code = 'The code must be started with:\n'
    starter_code += code

    if not feedback:
        message = 'Only write python3 code to answer the following question without any explanations:\n'
    else:
        message = 'Write python3 code to answer the following question and then explain your code:\n'
    message += description + examples + constraints + starter_code
    
    return message

def main(args):
    # Scrape the basic information of questions
    question_info = get_question_info()

    id_to_frontend_id = {}
    id_to_title = {}
    frontend_id_to_slug = {}
    title_to_slug = {}
    slug_to_paid_only = {}
    
    for info in question_info:
        id_to_frontend_id[info[0]] = info[1]
        id_to_title[info[0]] = info[2]
        frontend_id_to_slug[info[1]] = info[3]
        title_to_slug[info[2]] = info[3]
        slug_to_paid_only[info[3]] = info[5]
        
    # The result from 3 trials on 7 scopes of questions
    min_time_threads_num = {
        20: [11, 20, 21],
        30: [30, 20, 21],
        40: [38, 33, 25],
        50: [36, 30, 42],
        60: [47, 33, 21],
        70: [39, 55, 30],
        80: [50, 35, 40]
    }
    
    x = list(min_time_threads_num.keys())
    y = [(sum(value) / len(value)) / key for key, value in min_time_threads_num.items()]
    slope, intercept, _, _, _ = stats.linregress(x, y)

    def thread_to_question(x):
        return slope * x + intercept
            
    if args.query_type == 'id':
        # Scrape the detailed information of the given question and its similar questions
        slug = frontend_id_to_slug[args.id]
        question = get_question_by_slug(slug)
        start_time = time.time()
        question_slugs = [slug] + [info['titleSlug'] for info in question['similarQuestions']]
        question_slugs = list(filter(lambda x : not slug_to_paid_only[x], question_slugs))
    elif args.query_type == 'title':
        # Scrape the detailed information of the given question and its similar questions
        slug = title_to_slug[args.title]
        question = get_question_by_slug(slug)
        question_slugs = [slug] + [info['titleSlug'] for info in question['similarQuestions']]
        question_slugs = list(filter(lambda x : not slug_to_paid_only[x], question_slugs))
    elif args.query_type == 'difficulty':
        # Scrape the detailed information of the questions with the given difficulty
        difficulty_index = {'Easy': 1, 'Medium': 2, 'Hard': 3}
        question_slugs = [info[3] for info in question_info if info[4] == difficulty_index[args.difficulty]]
        question_slugs = list(filter(lambda x : not slug_to_paid_only[x], question_slugs))
    elif args.query_type == 'topic':
        # Scrape the detailed information of all questions and filter it at the end
        question_slugs = [info[3] for info in question_info]
        question_slugs = list(filter(lambda x : not slug_to_paid_only[x], question_slugs))
    else:
        raise Exception('Invalid query type')
    
    # Optimized point 1: Multi-threaded scraper for more detailed information
    
    questions = []
    lock = Lock()
    def get_question_by_slug_threading(q):
        while True:
            slug, flag = q.get()
            question = get_question_by_slug(slug, sleep = flag)
            with lock:
                questions.append(question)
            q.task_done()

    start_time = time.time()
    
    q = Queue()

    num_threads = round(max(0.1, thread_to_question(len(question_slugs))) * len(question_slugs))
    
    for i in range(num_threads):
        worker = Thread(target = get_question_by_slug_threading, args = (q, ))
        worker.setDaemon(True) 
        worker.start()

    flag = len(question_slugs) > 50
    for slug in question_slugs:
        q.put((slug, flag))

    q.join()
         
    end_time = time.time()
 
    print(f'Time for {num_threads} Threads: {end_time - start_time} seconds')
    
    if args.query_type == 'topic':
        questions = list(filter(lambda x : args.topic in x['topicTags'], questions))
    
    questions.sort(key = lambda x : x['questionId'])
    questions = questions[:args.upper_limit]
    
    print(f'The number of questions to be answered: {len(questions)}')
    
    # Optimized point 2: Multi-threaded ChatGPT requests
    
    openai.api_key = args.api_key
    
    replies = []
    lock = Lock()
    def get_chatGPT_reply_threading(q):
        while True:
            questionId, content, code, feedback = q.get()
            message = content_to_prompt(content, code, feedback)
            messages = [{'role': 'user', 'content': message}]
            chat_completion = openai.ChatCompletion.create(model = 'gpt-3.5-turbo', messages = messages)
            reply = chat_completion.choices[0].message.content
            with lock:
                replies.append((int(questionId), reply))
            q.task_done()

    start_time = time.time()
    
    q = Queue()

    num_threads = round(max(0.1, thread_to_question(len(questions))) * len(questions))
    
    for i in range(num_threads):
        worker = Thread(target = get_chatGPT_reply_threading, args = (q, ))
        worker.setDaemon(True) 
        worker.start()

    for question in questions:
        q.put((question['questionId'], question['content'], question['code'], args.feedback))

    q.join()

    replies.sort(key = lambda x : x[0])
         
    end_time = time.time()
 
    print(f'Time for {num_threads} Threads: {end_time - start_time} seconds')
    
    with open('./replies.txt','r+') as f:
        f.truncate(0)
    
    with open('./replies.txt', 'w') as f:
        for reply in replies:
            f.write(f'{id_to_frontend_id[reply[0]]}. {id_to_title[reply[0]]}\n{reply[1]}\n\n')

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--query_type', help = 'The query type includes id, title, difficulty and topic', 
                        default = 'id', type = str)
    parser.add_argument('--id', help = 'The frontend id of the question', 
                        default = 1, type = int)
    parser.add_argument('--title', help = 'The title of the question', 
                        default = 'Two Sum', type = str)
    parser.add_argument('--difficulty', help = 'The difficulty of the question (Easy/Medium/Hard)', 
                        default = 'Easy', type = str)
    parser.add_argument('--topic', help = 'The topic of the question (Array, String, Hash Table, etc.)', 
                        default = 'Array', type = str)
    parser.add_argument('--upper_limit', help = 'The upper limit of questions to be asked in one query', 
                        default = 50, type = bool)
    # Please enter your own OpenAI API key
    parser.add_argument('--api_key', help = 'The API key of your OpenAI account', 
                        required = True, type = str)
    parser.add_argument('--feedback', help = 'Do you want the feedback besides the code solution?', 
                        default = False, type = bool)
    
    args = parser.parse_args()
    main(args)