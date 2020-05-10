import nltk
import math
import json
from collections import Counter
nltk.download('punkt')
from notebook_parse import parse_ipynb

class Preprocessor:
    def __init__(self):
        self.stop_words = {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he', 'in', 'is', 'it', 'its',
                      'of', 'on', 'that', 'the', 'to', 'was', 'were', 'will', 'with'}
        self.ps = nltk.stem.PorterStemmer()
    # word tokenize text using nltk lib
    def tokenize(self, text):
        return nltk.word_tokenize(text)
    # stem word using provided stemmer
    def stem(self, word, stemmer):
        return stemmer.stem(word)
    # check if word is appropriate - not a stop word and isalpha, 
    # i.e consists of letters, not punctuation, numbers, dates
    def is_apt_word(self, word):
        return word not in self.stop_words and word.isalpha()
    # combines all previous methods together
    # tokenizes lowercased text and stems it, ignoring not appropriate words
    def preprocess(self, text):
        tokenized = self.tokenize(text.lower())
        return [self.stem(w, self.ps) for w in tokenized if self.is_apt_word(w)]

def update_inverted_index(files_data, doc_lengths, index, doc_index): # here we want to update only one notebook 
    prep = Preprocessor()
    for key in list(files_data.keys()):
        doc_id = key
        # print(f'Building index for {key}')
        content = prep.preprocess(files_data[key][0])
        doc_lengths[doc_id] = len(content) # here we just change previous values or create a new ones 
        see_first_time = doc_id in doc_index
        doc_index[doc_id] = files_data[key][1]
        # print(f'add len {doc_lengths} and ind {doc_index}')
        # get dict of terms in current article
        article_index = Counter(content)
        for term in article_index.keys():
            article_freq = article_index[term]
            if term not in index:  # if we have a new word in our notebook that is not in index, we add it as usual               
                index[term] = [article_freq, (doc_id, article_freq)]
            else: # here is a tricky part 
                previous_frequency = [x[1] for x in index[term][1:] if x[0] == doc_id]
                if not previous_frequency: # if this is first time this key in term index 
                    index[term][0] += article_freq # add new frequency 
                    index[term].append((doc_id, article_freq)) # add doc_id
                else: # if we have this key in index we update id 
                    index[term][0] -= previous_frequency[0] # remove previous frequency from total frequency
                    index[term] = [index[term][0]] + [x for x in index[term][1:] if x[0] != doc_id] # then i delete this tuple from list and add it again
                    index[term][0] += article_freq # add new frequency 
                    index[term].append((doc_id, article_freq)) # add doc_id  
    return  json.loads(json.dumps(index)), \
            json.loads(json.dumps(doc_lengths)),\
            json.loads(json.dumps(doc_index))

def find(raw_query, inverted_index, doc_lengths, doc_index, k1=1.2, b=0.75):
    # print(doc_lengths)
    prep = Preprocessor()
    query = Counter(prep.preprocess(raw_query))
    scores = {}
    N = len(doc_lengths)
    avgdl = sum(doc_lengths.values()) / float(len(doc_lengths))
    for term in query.keys():
        if term not in inverted_index:  # ignoring absent terms
            continue
        n_docs = len(inverted_index[term]) - 1
        print(N)
        print(n_docs)
        idf = math.log10((N - n_docs + 0.5) / (n_docs + 0.5))
        postings = inverted_index[term][1:]
        for posting in postings:
            doc_id = posting[0]
            doc_tf = posting[1]
            score = idf * doc_tf * (k1 + 1) / (doc_tf + k1 * (1 - b + b * (doc_lengths[(f'{doc_id}')] / avgdl)))
            if doc_id not in scores:
                scores[doc_id] = score
            else:  # accumulate scores
                scores[doc_id] += score
    documents = []
    for key in scores.keys():
        documents.append( (doc_index[(f'{key}')], scores[key]))
    documents.sort(key=lambda x: x[1], reverse=True)
    documents = [x[0] for x in documents]
    return documents