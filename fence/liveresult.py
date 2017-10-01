from bs4 import BeautifulSoup
import urllib.request, urllib.error, urllib.parse
import sqlite3
import re
import sys
import query
import calendar

def handleUSFAFencerList(url=None, table_conn=None, tournament_id=None):
    """
    Process the USFA Fencer List File
    """

    table_cur = table_conn.cursor()
    print(("Processing fencer list:", url))
    # retrieve the whole file
    f = open(url, "rU")

    table_conn.text_factory = str
    # extract fencers
    for line in f:
        fields = line.split(",")
        last_name = fields[0].strip().lower()
        first_name = fields[1].strip().lower()
        middle_name = fields[2].strip().lower()
        suffix = fields[3].strip()
        gender = fields[5].strip()
        membership = fields[14].strip()
        homeclub = fields[9].strip()
        citizenship = fields[23].strip()
        saberrate = fields[18].strip()
        epeerate = fields[19].strip()
        foilrate = fields[20].strip()
        table_cur.execute('SELECT * FROM fencers WHERE membership_number is ?', (membership,))
        cur = table_cur.fetchone()
        #print(membership, first_name, last_name, middle_name, suffix, gender, homeclub, citizenship, saberrate, epeerate, foilrate)
        table_cur.execute('INSERT OR REPLACE INTO fencers VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (membership, first_name, last_name, middle_name, suffix, gender, homeclub.upper(), citizenship, saberrate, epeerate, foilrate))

    table_conn.commit()


def handleUSFAResult(url=None, table_conn=None, tournament_id=None):
    """
    Process the main Result Page of USFA
    """

    print(("Processing event:", url))
    # retrieve the main page
    try:
        response = urllib.request.urlopen(url)
    except URLError as e:
        print(e.reason)
        return False

    soup = BeautifulSoup(response)
    tour_tag = soup.find("span", "tournName")

    # extract tournament information and save to Tournament Table
    tour_name = tour_tag.get_text().strip()
    if tour_name is None or len(tour_name) == 0:
        print("wrong page format")
        return False

    # extract event_id
    event_id_tag = soup.find("span", "tournDetails")
    event_id = event_id_tag.getText().strip()
    print(event_id)

    tour_day = 0
    tour_month = 0
    tour_year = 0
    matches = event_id.split(",")
    month_dict = {v: k for k,v in enumerate(calendar.month_name)}
    if len(matches) > 2:
        monthday = matches[1].strip().split(" ")
        tour_month = int(month_dict[monthday[0]])
        tour_day = int(monthday[1])
        tour_year = int(matches[2].split("-")[0])
    else:
        tour_date_tag = soup.find("span", "lastUpdate")
        tour_date = tour_date_tag.get_text()
        print(tour_date)
        tour_date = re.search(r"(\d+/\d+/\d+)", tour_date)
        tour_dates = re.split("/", tour_date.group(0))    
        tour_month = int(tour_dates[0])
        tour_day = int(tour_dates[1])
        tour_year = int(tour_dates[2])

    tournament_id = "usfa"+str(tour_year)+str(tour_month)+str(tour_day)
    print(tournament_id)
    table_cur = table_conn.cursor()
    if tournament_id and tour_name:
        #print "insert:", tournament_id
        table_cur.execute('INSERT OR REPLACE INTO tournament VALUES(?, ?, ?, ?, ?)',
                            (tournament_id, tour_name, tour_month,
                             tour_day, tour_year))
        table_conn.commit()


    ## Process the Pool Result, get all the pool tables
    table_tag_list = soup.find_all(name="table", class_="pool")
    tmp = re.findall("Foil|Epee|Saber", event_id)
    weapon_type = tmp[0]
    print(weapon_type)

    fencer_list = None
    # find each pool table
    pool_table_list = soup.find_all(name="table", class_="pool")
    for pool_table in pool_table_list:
        id_list = []
        score_list = []
        # find each tabe row
        tr_list = pool_table.find_all(name="tr", class_=["poolOddRow", "poolEvenRow"])
        for tr in tr_list:
            td_name = tr.find(name="td", class_="poolNameCol")
            span_name = td_name.find(name="span")
            span_text = span_name.get_text().strip()
            td_text = td_name.get_text()
            name = td_text.replace(span_text, "")
            name = name.split(",")
            lastname = name[0].strip().lower()
            firstname = name[1].strip()
            # handle stomething like this: Samuel (Sam) Moelis
            tmp = re.split("\(", firstname)
            firstname = tmp[0].strip().lower()
            span_fields = span_text.split("/")
            if len(span_fields) == 3:
                club = span_fields[0].strip()
            else:
                club = None
            citizenship = span_fields[-1].strip()
            table_cur.execute("SELECT * FROM fencers WHERE lastname is ? AND firstname is ?", (lastname, firstname,)) 
            cur = table_cur.fetchone()
            if cur:
                # found fencer in the database
                membership = cur[0]
            else:
                if club is None:
                    club = span_fields[0].strip()
                #print("INSERT:", firstname, lastname, club, citizenship)
                # this happens for foreign fencers
                # just make up a unique id
                membership = firstname + lastname + citizenship
                table_cur.execute('INSERT OR REPLACE INTO fencers VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (membership, firstname, lastname, "", "", "", "", citizenship, "", "", ""))
                table_conn.commit()


            id_list.append(membership)
            td_score_list = tr.find_all(name="td", class_=re.compile("poolScore[V|D]"))
            fencer_score = []
            for td in td_score_list:
                fencer_score.append(td.get_text().strip())

            score_list.append(fencer_score)

        # all the data in the pool is ready, pair them to bouts
        if len(id_list) > 0 and len(score_list) > 0:
            id_count = len(id_list)
            score_count = id_count - 1
            for i in range(0, id_count):
                for j in range(i, id_count):
                    if i==j:
                        continue
                    table_conn.execute('INSERT OR REPLACE INTO bouts VALUES(?, ?, ?, ?, ?, ?, ?, ?)', 
                                (id_list[i], id_list[j], score_list[i][j-1].lstrip("[V|D]"),
                                score_list[j][i].lstrip("[V|D]"), 0, weapon_type, tournament_id, event_id))

    table_conn.commit()
    # proceed to DE chart

    # find all elimination table
    de_table_list = soup.find_all(name="table", class_="elimTableau")
    for de_table in de_table_list:
        if "repApfTableau" in de_table['class']:
            handleRepafTableau(de_table, table_conn, weapon_type, tournament_id, event_id) 
        else:
            handleRegularTableau(de_table, table_conn, weapon_type, tournament_id, event_id) 

def handleRepafTableau(de_table=None, table_conn=None, weapon_type=None,
                         tournament_id=None, event_id=None):

    #print("handleRepafTableau")
    table_cur = table_conn.cursor()
    # figure out how many rounds are there
    round_number = []
    tr_list = de_table.find_all(name="tr")
    tr = tr_list[0]
    td_list = tr.find_all(name="td")
    for td in td_list:
        td_text = td.get_text().strip()
        if re.search("Table [A-Z]", td_text):
            # this is the case for repechage format
            match = re.search("\(.+\)", td_text)
            round = match.group(0).strip()
            match = re.search("[1-9]+", round)
            round = match.group(0).strip()
            tid = td_text.split("Table")
            tid = tid[1].strip()
            match = re.search("[A-Z]+", tid)
            tid = match.group(0).strip()
            round_number.append((tid, round))
        else:
            round_number.append(('X', 0))

    #print(round_number)

    # how many row
    row_number = len(tr_list) - 2
    
    # go through each table row, make them a big 2-dimension array
    raw_de_table = []
    i = 0
    j = 0
    # skip first 2 rows, which is "Table of xxx" and blank line
    for i in range(2, len(tr_list)):
        td_list = tr_list[i].find_all(name="td")
        raw_de_row = [0 for _ in range(0, len(td_list))]
        for j in range(0, len(td_list)):
            td_tag = td_list[j]
            name = td_tag.find_all(name="span", class_="tableauCompName")
            if len(name) > 0 and not re.search("BYE", name[0].get_text()):
                # this has a fencer name
                raw_de_row[j] = name[0].get_text().strip()
            else:
                # also look for match score field
                score_text = td_tag.get_text()
                match= re.search("[0-9]{1,2}.*-.*[0-9]{1,2}", score_text)
                if match:
                    raw_de_row[j] = match.group(0)
        #print(raw_de_row)
        raw_de_table.append(raw_de_row)

    #print(len(round_number))
    # now process each column, and match fencers to a bout
    # first process Table A and right of A
    found_a = 0
    p = 0
    for i in range(0, len(round_number) - 1):
        if found_a is 0:
            if 'A' not in round_number[i][0]:
                continue
            else: 
                found_a = i
        j = 0
        skip_count = 2 ** (p+1)
        first_found = False
        while j < row_number:
            # both cell has a fencer id
            fencer_1 = raw_de_table[j][i]
            fencer_2 = raw_de_table[j+skip_count][i]
            if fencer_1 != 0 and fencer_2 != 0:
                # j and j+skip_count is a pair
                # go skip_count*2 row ahead after the 1st fencer_id, we know j and j + skip_count*2
                # is the next pair
                # now find out what the score of this pair's match
                # check next column between row j and j+skip_count*2, mathc the score pattern
                fencer1_score = None
                fencer2_score = None
                fencer2_win = 0
                for k in range(0, skip_count+1):
                    score_text = raw_de_table[j+k][i+1]

                    # find out who win the bout
                    if score_text and fencer_2 in score_text:
                        fencer2_win = 1

                    if score_text and re.search("[0-9]{1,2}.*-.*[0-9]{1,2}", score_text):
                        fencer1_score = score_text.split("-")[0].strip()
                        fencer2_score = score_text.split("-")[1].strip()
                        break

                if fencer2_win:
                    # the winning score is always at the beginning, so swap the score
                    tmp = fencer2_score
                    fencer2_score = fencer1_score
                    fencer1_score = tmp

                # this is the match result
                if fencer1_score and fencer2_score:
                     name = raw_de_table[j][i].split(",")
                     lastname = name[0].strip().lower()
                     firstname = name[1].strip().lower()
                     # handle stomething like this: Samuel (Sam) Moelis
                     tmp = re.split("\(", firstname)
                     firstname = tmp[0].strip()
                     table_cur.execute('SELECT * FROM fencers WHERE firstname is ? and lastname is ?',
                                      (firstname, lastname,))
                     cur = table_cur.fetchone()
                     if cur is None:
                         print(("!!!not found", name))
                         id1 = 0
                     else:
                         id1 = cur[0]
                     name = raw_de_table[j+skip_count][i].split(",")
                     lastname = name[0].strip().lower()
                     firstname = name[1].strip().lower()
                     # handle stomething like this: Samuel (Sam) Moelis
                     tmp = re.split("\(", firstname)
                     firstname = tmp[0].strip()
                     table_cur.execute('SELECT * FROM fencers WHERE firstname is ? and lastname is ?',
                                      (firstname, lastname,))
                     cur = table_cur.fetchone()
                     if cur is None:
                         print(("!!!not found", name))
                         id2 = 0;
                     else:
                         id2 = cur[0]
                     #print(raw_de_table[j][i], id1, raw_de_table[j+skip_count][i], id2,
                     #      fencer1_score, fencer2_score, round_number[i][1], weapon_type, tournament_id, event_id)
                     table_cur.execute('INSERT OR REPLACE INTO bouts VALUES(?, ?, ?, ?, ?, ?, ?, ?)', 
                                        (id1, id2, int(fencer1_score), int(fencer2_score), int(round_number[i][1]),
                                         weapon_type, tournament_id, event_id))
                
                j = j + skip_count*2
                first_found = True
            elif not first_found:
                # go 1 row at a time before finding the 1st fencer_id
                j = j + 1
            else:
                # go skip_count*2 row ahead after the 1st fencer_id, we know j and j + skip_count*2
                # is the next pair
                j = j + skip_count*2
        p = p + 1

    # second process Table A and left of A
    p = 1
    i = found_a - 1
    while i > 0:
        j = 0
        skip_count = 2 ** (p+1)
        first_found = False
        while j < row_number:
            # both cell has a fencer id
            fencer_1 = raw_de_table[j][i]
            fencer_2 = raw_de_table[j+skip_count][i]
            if fencer_1 != 0 and fencer_2 != 0:
                # j and j+skip_count is a pair
                # go skip_count*2 row ahead after the 1st fencer_id, we know j and j + skip_count*2
                # is the next pair
                # now find out what the score of this pair's match
                # check next column between row j and j+skip_count*2, mathc the score pattern
                fencer1_score = None
                fencer2_score = None
                fencer2_win = 0
                for k in range(0, skip_count+1):
                    score_text = raw_de_table[j+k][i-1]

                    # find out who win the bout
                    if score_text and fencer_2 in score_text:
                        fencer2_win = 1

                    if score_text and re.search("[0-9]{1,2}.*-.*[0-9]{1,2}", score_text):
                        fencer1_score = score_text.split("-")[0].strip()
                        fencer2_score = score_text.split("-")[1].strip()
                        break

                if fencer2_win:
                    # the winning score is always at the beginning, so swap the score
                    tmp = fencer2_score
                    fencer2_score = fencer1_score
                    fencer1_score = tmp

                # this is the match result
                if fencer1_score and fencer2_score:
                     name = raw_de_table[j][i].split(",")
                     lastname = name[0].strip().lower()
                     firstname = name[1].strip().lower()
                     # handle stomething like this: Samuel (Sam) Moelis
                     tmp = re.split("\(", firstname)
                     firstname = tmp[0].strip()
                     table_cur.execute('SELECT * FROM fencers WHERE firstname is ? and lastname is ?',
                                      (firstname, lastname,))
                     cur = table_cur.fetchone()
                     if cur is None:
                         print(("!!!not found", name))
                         id1 = 0
                     else:
                         id1 = cur[0]
                     name = raw_de_table[j+skip_count][i].split(",")
                     lastname = name[0].strip().lower()
                     firstname = name[1].strip().lower()
                     # handle stomething like this: Samuel (Sam) Moelis
                     tmp = re.split("\(", firstname)
                     firstname = tmp[0].strip()
                     table_cur.execute('SELECT * FROM fencers WHERE firstname is ? and lastname is ?',
                                      (firstname, lastname,))
                     cur = table_cur.fetchone()
                     if cur is None:
                         print(("!!!not found", name))
                         id2 = 0;
                     else:
                         id2 = cur[0]
                     #print(raw_de_table[j][i], id1, raw_de_table[j+skip_count][i], id2,
                     #      fencer1_score, fencer2_score, round_number[i][1], weapon_type, tournament_id, event_id)
                     table_cur.execute('INSERT OR REPLACE INTO bouts VALUES(?, ?, ?, ?, ?, ?, ?, ?)', 
                                        (id1, id2, int(fencer1_score), int(fencer2_score), int(round_number[i][1]),
                                         weapon_type, tournament_id, event_id))
                
                j = j + skip_count*2
                first_found = True
            elif not first_found:
                # go 1 row at a time before finding the 1st fencer_id
                j = j + 1
            else:
                # go skip_count*2 row ahead after the 1st fencer_id, we know j and j + skip_count*2
                # is the next pair
                j = j + skip_count*2
        p = p + 1
        i = i - 1

    table_conn.commit()
    return True


def handleRegularTableau(de_table=None, table_conn=None, weapon_type=None,
                         tournament_id=None, event_id=None):

    #print("handleRegularTableau")
    table_cur = table_conn.cursor()
    # figure out how many rounds are there
    round_number = []
    tr_list = de_table.find_all(name="tr")
    tr = tr_list[0]
    td_list = tr.find_all(name="td")
    for td in td_list:
        td_text = td.get_text().strip()
        if re.search("Table of", td_text):
            round_number.append(td_text.split("Table of")[1].strip())
        elif re.search("Semi-Finals", td_text):
            round_number.append("4")
        elif re.search("Finals", td_text):
            round_number.append("2")
        elif re.search("Table [A-Z]", td_text):
            # this is the case for repechage format
            match = re.search("\(.+\)", td_text)
            round = match.group(0).strip()
            match = re.search("[1-9]+", round)
            round = match.group(0).strip()
            round_number.append(round)

    #print(round_number)

    # how many row
    row_number = len(tr_list) - 2
    
    # go through each table row, make them a big 2-dimension array
    raw_de_table = []
    i = 0
    j = 0
    # skip first 2 rows, which is "Table of xxx" and blank line
    for i in range(2, len(tr_list)):
        raw_de_row = [0 for _ in range(0, len(round_number)+1)]
        td_list = tr_list[i].find_all(name="td")
        for j in range(0, len(td_list)):
            td_tag = td_list[j]
            name = td_tag.find_all(name="span", class_="tableauCompName")
            if len(name) > 0 and not re.search("BYE", name[0].get_text()):
                # this has a fencer name
                raw_de_row[j] = name[0].get_text().strip()
            else:
                # also look for match score field
                score_text = td_tag.get_text()
                match= re.search("[0-9]{1,2}.*-.*[0-9]{1,2}", score_text)
                if match:
                    raw_de_row[j] = match.group(0)
        #print(raw_de_row)
        raw_de_table.append(raw_de_row)

    # now process each column, and match fencers to a bout
    i = 0
    for i in range(0, len(round_number)):
        j = 0
        skip_count = 2 ** (i+1)
        first_found = False
        while j < row_number:
            # both cell has a fencer id
            fencer_1 = raw_de_table[j][i]
            fencer_2 = raw_de_table[j+skip_count][i]
            if fencer_1 != 0 and fencer_2 != 0:
                # j and j+skip_count is a pair
                # go skip_count*2 row ahead after the 1st fencer_id, we know j and j + skip_count*2
                # is the next pair
                # now find out what the score of this pair's match
                # check next column between row j and j+skip_count*2, mathc the score pattern
                fencer1_score = []
                fencer2_score = []
                fencer2_win = 0
                for k in range(0, skip_count+1):
                    score_text = raw_de_table[j+k][i+1]
                    # if this is a Y10 or older date Y12, there is up to 3 bouts
                    if score_text:
                        # find out who win the bout
                        if fencer_2 in score_text:
                            fencer2_win = 1
                        search_result = re.search("[0-9]{1,2}.*-.*[0-9]{1,2}", score_text)
                        if search_result:
                            search_result = search_result.group(0)
                            search_result = search_result.split(",")
                            for l in range(0, len(search_result)):
                                tmp_score = search_result[l].split("-")
                                fencer1_score.append(tmp_score[0].strip())
                                fencer2_score.append(tmp_score[1].strip())
                            #print fencer1_score, fencer2_score
                            break

                if fencer2_win:
                    # the winning score is always at the beginning, so swap the score
                    tmp = fencer2_score
                    fencer2_score = fencer1_score
                    fencer1_score = tmp

                # this is the match result
                if fencer1_score and fencer2_score:
                     name = fencer_1.split(",")
                     lastname = name[0].strip().lower()
                     firstname = name[1].strip().lower()
                     # handle stomething like this: Samuel (Sam) Moelis
                     tmp = re.split("\(", firstname)
                     firstname = tmp[0].strip()
                     table_cur.execute('SELECT * FROM fencers WHERE firstname is ? and lastname is ?',
                                      (firstname, lastname,))
                     cur = table_cur.fetchone()
                     if cur is None:
                         print(("!!!not found", name))
                         id1 = 0
                     else:
                         id1 = cur[0]
                     name = fencer_2.split(",")
                     lastname = name[0].strip().lower()
                     firstname = name[1].strip().lower()
                     # handle stomething like this: Samuel (Sam) Moelis
                     tmp = re.split("\(", firstname)
                     firstname = tmp[0].strip()
                     table_cur.execute('SELECT * FROM fencers WHERE firstname is ? and lastname is ?',
                                      (firstname, lastname,))
                     cur = table_cur.fetchone()
                     if cur is None:
                         print(("!!!not found", name))
                         id2 = 0;
                     else:
                         id2 = cur[0]
                     for x in range(0, len(fencer1_score)):
                         #print(fencer_1, id1, fencer_2, id2, fencer1_score[x], fencer2_score[x], round_number[i], weapon_type, tournament_id, event_id)
                         table_cur.execute('INSERT OR REPLACE INTO bouts VALUES(?, ?, ?, ?, ?, ?, ?, ?)', 
                                            (id1, id2, int(fencer1_score[x]), int(fencer2_score[x]), int(round_number[i]),
                                             weapon_type, tournament_id, event_id))
                
                j = j + skip_count*2
                first_found = True
            elif not first_found:
                # go 1 row at a time before finding the 1st fencer_id
                j = j + 1
            else:
                # go skip_count*2 row ahead after the 1st fencer_id, we know j and j + skip_count*2
                # is the next pair
                j = j + skip_count*2

    table_conn.commit()
    return True
