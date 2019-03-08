from utils import *
import pandas as pd
from pdfplumber.utils import extract_words
import json
import sys


"""
Usage: python test_functions.py <filename> <page_number> <json_file>
    
    where filename: input pdf file
    page_number: page number of the input pdf file and starts with 0
    json file: example json file for the pdf

"""


"""
file     page_num
ex1      1
ex2      0
ex3
ex4
test     0
"""



############## Load file ################
input_filename = sys.argv[1]
pagenum = int(sys.argv[2])
json_filename = sys.argv[3]

pdf = PDF(input_filename, page_num=pagenum)

## Extracting the words from the pdf
words = extract_words(pdf.page.chars)


## Dataframe which contains words separately
pdf.single_df = pd.DataFrame(words)

combined_words = combine(words, "words", 
                         x_tolerance=6, 
                         y_tolerance=5, 
                         keep_blank_chars=False)

## Dataframe which contains words in combined form
pdf.words_df = pd.DataFrame(combined_words)




############ Read json ######################

with open(json_filename, 'r') as f:
    datas = json.load(f)




############# Write each data in json #################
for data in datas:
    print("writing:",data)

    to_write = data['value']

    # Text
    if data['dataType'] == 'text' or data['dataType'] == 'number':
        pdf.write_txt(data['exportLabel'], to_write)

    # Date
    if data['dataType'] == 'date':
        pdf.write_date(data['exportLabel'], to_write)

    # Checkbox
    if data['dataType'] == 'select':
        pdf.write_checkbox(data['exportLabel'], to_write)





########## Finally, export to pdf (in-place) ###############
pdf.write_to_pdf()

