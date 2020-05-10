import io
import json
import re

def parse_ipynb(notebook_json): 
    # with open(path) as f:
    #     notebook_json = json.load(f)

    text = 'start'
    imports = []
    functions = []
    loops = []
    classes = []
    installations = []

    for_name = 0
    for cell in notebook_json['cells']:
        fun_flag = 0
        for_flag = 0
        class_flag = 0
        if cell['cell_type'] == 'code':
            for elem in cell['source']:

                # find comments 
                if len(elem.split("#",1)) == 2:
                    text += ' ' + elem.split("#",1)[1].rstrip()

                if fun_flag == 1 and elem.startswith(' '):
                    functions += elem
                    continue

                elif fun_flag == 1 and not elem.startswith(' '):
                    fun_flag == 0

                elif for_flag == 1 and elem.startswith(' '):
                    loops += elem
                    continue
                
                elif for_flag == 1 and not elem.startswith(' '):
                    for_flag == 0

                elif class_flag == 1 and elem.startswith(' '):
                    classes += elem
                    continue

                elif class_flag == 1 and not elem.startswith(' '):
                    class_flag == 0

                elif elem.startswith('!pip install'):
                    installations.append(elem.rstrip().replace('!pip install',''))
                
                elif elem.startswith('import') or elem.startswith('from'):
                    installations.append(elem.rstrip())

                elif elem.startswith('def '):
                    fun_name = ' '.join(re.search('def (.*)\(', elem).group(1).split("_"))
                    text += ' ' + fun_name 
                    if not functions:
                        functions = '\n' + elem
                    else:
                        functions += '\n '
                        functions += '\n' + elem
                    fun_flag = 1

                elif elem.startswith('for '):
                    if not loops:
                        loops = '\n' + elem
                    else:
                        loops += '\n '
                        loops += '\n' + elem
                    for_flag = 1

                elif elem.startswith('class '):
                    if not classes:
                        classes = '\n' + elem
                    else:
                        classes += '\n '
                        classes += '\n' + elem
                    class_flag = 1

        if cell['cell_type'] == 'markdown':
            for elem in cell['source']:
                if elem != '\n':
                    text += ' ' + elem.rstrip()
        
        # here I convert dict to json 
        dict = {'functions': functions,
            'classes': classes, 
            'loops': loops,
            'text': text}
        a = json.dumps(dict)
        out = json.loads(a)

    return out