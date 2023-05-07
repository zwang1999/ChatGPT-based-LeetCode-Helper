
import openai

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

def get_chatGPT_reply_multiprocessing(questionId, content, code, api_key, feedback):
    openai.api_key = api_key
    message = content_to_prompt(content, code, feedback)
    messages = [{'role': 'user', 'content': message}]
    chat_completion = openai.ChatCompletion.create(model = 'gpt-3.5-turbo', messages = messages)
    reply = chat_completion.choices[0].message.content
    return (int(questionId), reply)
