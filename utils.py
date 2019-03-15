import pdfplumber
from pdfplumber.utils import cluster_objects, objects_to_bbox
from operator import itemgetter
import itertools
from decimal import Decimal
import pandas as pd
import numpy as np
import os
from dateutil.parser import parse
from deprecated import deprecated


class PDF:
    # PDF elements
    input_filename = ""
    pdf = None
    page = None
    page_num=0

    # Dataframes
    chars_df = None
    words_df = None
    single_df = None

    # Statistics about the current document
    symbol_stats = None
    
    # Keep changes in a list, to write later
    changes = []


    def __init__(self, input_filename, page_num=0):
        self.page_num=page_num
        self.input_filename = input_filename
        self.pdf = pdfplumber.open(input_filename)

        self.page = self.pdf.pages[page_num]
        self.chars_df = pd.DataFrame(self.page.chars)
        
        self.check_pageStats()


    def check_pageStats(self):
        """
        Calculates document statistics, updates self.symbol_stats

        In some documents, dots/checkboxes are character (selectable). In some, they are only in "pdf.rects" (not selectable)
        For some functions, we need to check this first.

        :return:
        """

        ### Check chars (selectable)
        df_chars_all = pd.DataFrame(self.pdf.chars)
        
        special_chars = {'…':0, '.':0, '...':0, '_':0, '___':0, '':0, '|___|':0}

        s="".join([c for c in df_chars_all.text.get_values()])
        for key in special_chars.keys():
            char = key
            
            perc = s.count(char) / len(s) * 100
            
            special_chars[key] += perc
            print("% of ", char, "\t\t", perc)

        ### Check rects (unselectable)
        df_rects_all = pd.DataFrame(self.pdf.rects)
        
        ### Dots as rects
        dots = df_rects_all[(df_rects_all['width'] < 3) & (df_rects_all['height'] < 1)]

        ### Checkboxes as rects
        df_rects_all['diff_wh'] = abs(df_rects_all['width'] - df_rects_all['height'])
        checkboxes = df_rects_all[(df_rects_all['diff_wh'] < 1) & (df_rects_all['width'] > 2)]
        
        print('% of dots as rect \t\t', len(dots) / len(df_rects_all) * 100)
        print('% of checkboxes as rect \t', len(checkboxes) / len(df_rects_all) * 100)

        special_chars['unselectable_dots'] = len(dots) / len(df_rects_all) * 100
        special_chars['unselectable_checkboxes'] = len(checkboxes) / len(df_rects_all) * 100
        
        self.symbol_stats = special_chars


    def get_writeCoords(self, val):
        """
        Get the writing coordinates

        :param val: Pandas series, export label from df
        :return: x and y locations (where to write)
        """
        text = val['text']

        x = (float)(val['x1'])
        y = (float)(self.page.bbox[3] - (val['bottom']))

        # If the text has multiple trailing dots, update x coordinate
        if text.endswith('.....'):
            dotcount = text.count('.')
            dotwidth = (float)(self.chars_df[self.chars_df['text'] == '.'].iloc[0].width)

            for i in range(dotcount):
                x -= dotwidth
        x += 1
        return x,y


    def write_txt(self, exportLabel, value):
        """
        Write normal text value

        :param exportLabel: Comes from the JSON, what to fill (ex: "UPN Number")
        :param value: Value to be written  (ex: "325241")
        :return:
        """
        # Get the export label from df
        val = self.words_df[self.words_df['text'].str.contains(exportLabel)]
        val = val.iloc[0]

        x,y = self.get_writeCoords(val)

        self.changes.append((x,y,value))


    def write_date(self, exportLabel, value, dateformat = "dd-mm-yyyy"):
        """
        Write date value

        :param exportLabel: Comes from the JSON, what to fill (ex: "Report date")
        :param value: Value to be written  (ex: "01/12/2018")
        :param dateformat: Denotes how to write the date
        :return:
        """
        val = self.words_df[self.words_df['text'].str.contains(exportLabel)]

        x = (float)(val['x1'])
        y = (float)(self.page.bbox[3] - (val['bottom']))
        dt = parse(value)
           
        # Construct the date string
        datestring = ""
        for el in dateformat.split('-'):
            if el == "dd":
                datestring += str(dt.day)
            if el == "mm":
                datestring += str(dt.month)
            if el == "yyyy":
                datestring += str(dt.year)
            datestring += "-"
            
        datestring = datestring[:-1]

        self.changes.append((x,y,datestring))
        

    def check_dist(self, words_df, exportLabel, val):
        """
        If there are multiple values, returns the index of the closest one

        :param words_df: Dataframe to check within
        :param exportLabel: Comes from the JSON, what to fill
        :param val: Value to be written
        :return:
        """
        rect_val_list = []

        exp = words_df[words_df['text'].str.contains(exportLabel)].values[0]
        exp_rect = (lookup_windowAround(exp))
        print(exp_rect)

        for x, i in enumerate(val):
            # print(i)
            rect_val = (lookup_windowAround(i))
            rect_val_list.insert(x, rect_val)

        min_dist = 99999
        for i, rect_val in enumerate(rect_val_list):
            a = np.array((exp_rect['x0'], exp_rect['top']))
            b = np.array((rect_val['x0'], rect_val['top']))
            dist = np.linalg.norm(a - b)
            if (dist < min_dist):
                min_dist = dist
                index = i

        return val[index]
        
        
    def selectable_checkbox(self, rects, value, exportLabel):
        """
        Called from write_checkbox()

        :param rects:
        :param value:
        :return:
        """
        aim_rects = []

        if (' ' in value):
            v = self.words_df[self.words_df['text'].str.contains(value)]
            val = self.words_df[self.words_df['text'].str.contains(value)].values

        else:
            v = self.single_df[self.single_df['text'] == value]
            val = self.single_df[self.single_df['text'] == value].values


        if (len(val) > 1):  # if there are 2 same values
            index = self.check_dist(self.words_df, exportLabel, val)
            aim_rect = lookup_windowAround(index)  ## check here if close to exportlabel
            aim_rects.append(aim_rect)

        else:
            index = val[0]
            aim_rect = lookup_windowAround(index)
            aim_rects.append(aim_rect)

        for aim_rect in aim_rects:

            if (v['text'].values[0] == value):
                if ((aim_rect['x0'] < v['x0'].values[0]) & (aim_rect['x1'] > v['x1'].values[0]) & (
                        aim_rect['top'] < v['top'].values[0]) & (aim_rect['bottom'] > v['bottom'].values[0])):
                    y = (float)(self.page.bbox[3] - v['bottom'])
                    x = (float)(v['x0'])
                    self.changes.append((x, y, "X"))


    @deprecated(reason="Writing 'X' on top of the value right now, not searching for checkboxes")
    def unselectable_checkbox(self, rects, value, exportLabel):
        """ Deprecated """
        aim_rects = []

       # if(' ' in value):
        val = self.words_df[self.words_df['text'].str.contains(value)].values
      #  else:
          #  val = self.single_df[self.single_df['text'].str.contains(value)].values
   
        #val = v.values      
        print("val:",val)
        if (len(val) > 1):  # if there are 2 same values
            v = self.check_dist(self.words_df, exportLabel, val)
            aim_rect = lookup_windowAround(v)  ## check here if close to exportlabel
            aim_rects.append(aim_rect)

        else:
            v = val[0]
            print(v)
            aim_rect = lookup_windowAround(v)
            aim_rects.append(aim_rect)


        for aim_rect in aim_rects:
            for rect in rects:
                w = abs(rect['x1'] - rect['x0'])
                h = abs(rect['bottom'] - rect['top'])

                ### checking if box
                if abs(w - h) < 1 and w > 2:  ##if there is a checkbox inside the bounding box
                    if ((aim_rect['x0'] < rect['x0']) & (aim_rect['x1'] > rect['x1']) & (
                            aim_rect['top'] < rect['top']) & (aim_rect['bottom'] > rect['bottom'])):
                        print(rect)
                        y = (float)(self.page.bbox[3] - rect['bottom'])
                        x = (float)(rect['x0'])
                        self.changes.append((x, y, "X"))


    def write_checkbox(self, exportLabel, value):
        """
        Ticks the checkbox

        :param exportLabel: Comes from the JSON, what to tick (ex: Sex)
        :param value: Which option to tick, from (ex: Female)
        :return:
        """

        rects = self.page.chars
        self.selectable_checkbox(rects,value,exportLabel)


    def write_to_pdf(self):
        """
        Write all changes one by one to pdf (in-place!)

        :return:
        """

        for x, y, val in self.changes:
            command = "cpdf -add-text '%s' -color 'red' -pos-left '%s %s' %s %s -o %s" % (str(val), str(x), str(y), self.input_filename, str(self.page_num+1), self.input_filename)
            print("Executing:",command)
            os.system(command)



########## Global functions


def combine(obj, attr, x_tolerance=3, y_tolerance=3, keep_blank_chars=False):
    """

    General combine function

        chars --> words
            or
        words --> combined_words

    :param obj: char list or words list, in pdfplumber format
    :param attr:  "chars" or "words", denoting what to combine
    :return: combined_objs
    """

    def process_word_chars(chars):
            x0, top, x1, bottom = objects_to_bbox(chars)
            return {
                "x0": x0,
                "x1": x1,
                "top": top,
                "bottom": bottom,
                "text": " ".join(map(itemgetter("text"), chars))
            }

    def get_line_words(chars, tolerance=3):
        get_text = itemgetter("text")
        chars_sorted = sorted(chars, key=itemgetter("x0"))
        words = []
        current_word = []

        for char in chars_sorted:
            if not keep_blank_chars and get_text(char).isspace():
                if len(current_word) > 0:
                    words.append(current_word)
                    current_word = []
                else: pass
            elif len(current_word) == 0:
                current_word.append(char)
            else:
                last_char = current_word[-1]
                if char["x0"] > (last_char["x1"] + tolerance):
                    words.append(current_word)
                    current_word = []
                current_word.append(char)

        if len(current_word) > 0:
            words.append(current_word)
        processed_words = list(map(process_word_chars, words))
        return processed_words

    ### cluster_objects requires different things for combining chars/words
    if attr == "chars":
        attr = "doctop"
    elif attr == "words":
        attr = "top"

    clusters = cluster_objects(obj, attr, y_tolerance)
    nested = [ get_line_words(line_chars, tolerance=x_tolerance)
            for line_chars in clusters ]

    combined_objs = list(itertools.chain(*nested))
    return combined_objs




def lookup_windowAround(bbox):
    """
    Returns a bigger rectange around given bbox

    :param bbox:
    :return: rect_around
    """

    bottom,_,top,x0,x1 = bbox
    
    window = 20
    half_window = Decimal(window/2)
    twice_window = Decimal(window*2)
    
    rect_around = {'x0':x0-window, 'top':top-half_window, 'x1':x1+half_window, 'bottom':bottom+half_window,}

    return rect_around



