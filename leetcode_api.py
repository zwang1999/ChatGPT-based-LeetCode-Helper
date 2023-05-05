import json
import leetcode
import leetcode.auth
import time

def setup():
    with open('accounts_info.json') as f:
        info = json.load(f)

    leetcode_session = info['leetcode_session']
    csrf_token = leetcode.auth.get_csrf_cookie(leetcode_session)

    configuration = leetcode.Configuration()

    configuration.api_key['x-csrftoken'] = csrf_token
    configuration.api_key['csrftoken'] = csrf_token
    configuration.api_key['LEETCODE_SESSION'] = leetcode_session
    configuration.api_key['Referer'] = 'https://leetcode.com'
    configuration.debug = False

    api_instance = leetcode.DefaultApi(leetcode.ApiClient(configuration))
    
    return api_instance

def status_check(api_instance):
    graphql_request = leetcode.GraphqlQuery(
        query = '''
            {
                user {
                    username
                isCurrentUserPremium
                }
            }
        ''',
        variables = leetcode.GraphqlQueryVariables(),
    )
    print(api_instance.graphql_post(body = graphql_request))

def submission(api_instance, question_id, code, lang = 'python3'):
    submission = leetcode.Submission(
        judge_type = 'large',
        typed_code = code,
        question_id = question_id,
        test_mode = False,
        lang = lang
    )

    interpretation_id = api_instance.problems_problem_submit_post(
        problem = 'two-sum', 
        body = submission
    )
    print("Submission has been queued. ID:")
    print(interpretation_id)
    
    result = None
    while not result or result['state'] == 'STARTED' or result['state'] == 'PENDING':
        time.sleep(5)
        result = api_instance.submissions_detail_id_check_get(
            id = interpretation_id.submission_id
        )
    return result