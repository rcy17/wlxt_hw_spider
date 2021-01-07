from argparse import ArgumentParser
from getpass import getpass
from urllib.parse import urlencode, parse_qs, urljoin
from pathlib import Path
import re


import pyunpack
from tqdm import tqdm
from requests import Session


def parse_args():
    parser = ArgumentParser(description='用于助教从网络学堂逐一批量下载较大的作业\n'
                            '最初为 DSA PA2b 设计')
    parser.add_argument('-u', '--username', type=str, help='用户名，info帐号和学号都可以')
    parser.add_argument('-p', '--password', type=str,
                        help='info密码，如果担心暴露给旁边人可以留空，会无回显输入')
    parser.add_argument('-c', '--course', default='数据结构',
                        type=str, help='完成课程名，将被精确匹配，默认为数据结构')
    parser.add_argument('-i', '--homework_id', default=3,
                        type=int, help='作业号，请在网络学堂作业页面查看，默认3为数据结构PA2b作业')
    parser.add_argument('-f', '--force', action='store_true', help='强制重下，暂时无用')
    parser.add_argument('-d', '--dir', default='data',
                        type=str, help='存储下载结果的文件夹，默认为data')
    return parser.parse_args()


def login(s: Session, username: str = None, password: str = None):
    url = 'https://id.tsinghua.edu.cn/do/off/ui/auth/login/post/bb5df85216504820be7bba2b0ae1535b/0?/login.do'
    data = {
        'i_user': username or input('username: '),
        'i_pass': password or getpass(),
    }
    r = s.post(url, data=data).text
    try:
        ticket = re.search(r'ticket=(\w+)', r).group(1)
    except AttributeError:
        raise ValueError('用户名或密码错误')
    url = f'https://learn.tsinghua.edu.cn/f/login.do?status=SUCCESS&ticket={ticket}'
    assert s.get(url).status_code == 200
    url = f'https://learn.tsinghua.edu.cn/b/j_spring_security_thauth_roaming_entry?ticket={ticket}'
    assert s.get(url).status_code == 200


def get_course(s: Session, course_name: str):
    url = 'https://learn.tsinghua.edu.cn/b/kc/v_wlkc_kcb/queryAsorCoCourseList/2020-2021-1/0'
    courses = s.get(url).json()
    for course in courses['resultList']:
        if course['kcm'] == course_name:
            return course
    raise ValueError('无法在当前学期的助教课程中找到课程' + course['kcm'])


def get_homework(s: Session, course: dict, homework_id: int):
    data = '[{"name":"sEcho","value":1},{"name":"iColumns","value":8},{"name":"sColumns","value":",,,,,,,"},'\
           '{"name":"iDisplayStart","value":0},{"name":"iDisplayLength","value":"-1"},{"name":"mDataProp_0",'\
           '"value":"wz"},{"name":"bSortable_0","value":true},{"name":"mDataProp_1","value":"function"},'\
           '{"name":"bSortable_1","value":false},{"name":"mDataProp_2","value":"function"},'\
           '{"name":"bSortable_2","value":false},{"name":"mDataProp_3","value":"function"},'\
           '{"name":"bSortable_3","value":false},{"name":"mDataProp_4","value":"function"},'\
           '{"name":"bSortable_4","value":false},{"name":"mDataProp_5","value":"kssj"},'\
           '{"name":"bSortable_5","value":true},{"name":"mDataProp_6","value":"jzsj"},'\
           '{"name":"bSortable_6","value":true},{"name":"mDataProp_7","value":"function"},'\
           '{"name":"bSortable_7","value":false},{"name":"iSortCol_0","value":0},'\
           '{"name":"sSortDir_0","value":"desc"},{"name":"iSortingCols","value":1},'\
           '{"name":"wlkcid","value":"%s"}]' % course['wlkcid']
    url = 'https://learn.tsinghua.edu.cn/b/wlxt/kczy/zy/teacher/pageList'
    result = s.post(url, data={'aoData': data}).json()
    for homework in result['object']['aaData']:
        if homework['wz'] == homework_id:
            return homework
    raise ValueError(
        f'无法在课程{course["wlkcid"]}-{course["kcm"]}中找到作业号为{homework_id}的作业')


def download(s: Session, homework: dict, directory: Path):
    data = '[{"name":"sEcho","value":1},{"name":"iColumns","value":12},{"name":"sColumns","value":",,,,,,,,,,,"},'\
           '{"name":"iDisplayStart","value":0},{"name":"iDisplayLength","value":"-1"},{"name":"mDataProp_0",'\
           '"value":"function"},{"name":"bSortable_0","value":false},{"name":"mDataProp_1","value":"qzmc"},'\
           '{"name":"bSortable_1","value":true},{"name":"mDataProp_2","value":"xh"},{"name":"bSortable_2",'\
           '"value":true},{"name":"mDataProp_3","value":"xm"},{"name":"bSortable_3","value":true},'\
           '{"name":"mDataProp_4","value":"dwmc"},{"name":"bSortable_4","value":false},'\
           '{"name":"mDataProp_5","value":"bm"},{"name":"bSortable_5","value":false},'\
           '{"name":"mDataProp_6","value":"xzsj"},{"name":"bSortable_6","value":true},'\
           '{"name":"mDataProp_7","value":"scsjStr"},{"name":"bSortable_7","value":false},'\
           '{"name":"mDataProp_8","value":"pyzt"},{"name":"bSortable_8","value":true},'\
           '{"name":"mDataProp_9","value":"cj"},{"name":"bSortable_9","value":true},'\
           '{"name":"mDataProp_10","value":"jsm"},{"name":"bSortable_10","value":true},'\
           '{"name":"mDataProp_11","value":"function"},{"name":"bSortable_11","value":false},'\
           '{"name":"iSortCol_0","value":2},{"name":"sSortDir_0","value":"asc"},{"name":"iSortingCols","value":1},'\
           '{"name":"zyid","value":"%s"},{"name":"wlkcid","value":"%s"}]' % (
               homework['zyid'], homework['wlkcid'])
    url = 'https://learn.tsinghua.edu.cn/b/wlxt/kczy/xszy/teacher/getDoneInfo'
    students = s.post(url, data={'aoData': data}).json()['object']['aaData']
    directory = directory / homework['bt']
    directory.mkdir(parents=True, exist_ok=True)
    for student in tqdm(students):
        base_url = 'https://learn.tsinghua.edu.cn/b/wlxt/kczy/xszy/teacher/downloadFile'
        url = f'{base_url}/{homework["wlkcid"]}/{student["zyfjid"]}'
        headers = s.head(url).headers
        raw_filename = re.search(
            'filename="(.*?)"', headers['Content-Disposition']).group(1)
        suffix = Path(raw_filename).suffix
        filename = f'{student["xh"]}-{student["xm"]}' + suffix
        path = directory / filename
        size = int(headers['Content-Length'])
        if path.is_file() and path.stat().st_size == size:
            continue
        response = s.get(url, stream=True)
        assert response.status_code == 200
        with open(path, 'wb') as file:
            for chunk in tqdm(response.iter_content(32768)):
                if chunk:
                    file.write(chunk)
        if path.suffix in ['.rar', '.zip', '7z']:
            arch = pyunpack.Archive(path)
            extract_to = directory / path.stem
            extract_to.mkdir(exist_ok=True)
            try:
                arch.extractall(directory=extract_to)
            except Exception as e:
                print(type(e).mro()[0], *e.args)
                print('Failed to extract', path)
        else:
            print('无法识别压缩文件', path)


def main(args):
    s = Session()
    login(s, args.username, args.password)
    course = get_course(s, args.course)
    homework = get_homework(s, course, args.homework_id)
    download(s, homework, Path(args.dir))


if __name__ == "__main__":
    main(parse_args())
