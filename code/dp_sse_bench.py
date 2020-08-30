import dp_sse 
import json
import time 
import random 
import sys 
from collections import defaultdict

class dp_sse_bench:
    def __init__(self):
        self.db_fn = "../db/enron_db_no_stopwords_size_limit.json"
        self.db_inverted_fn = "../db/enron_inverted_index_ordered.json"
        self.pt_index_fn = "../db/plaintext_index.json"
        self.pt_index_bench_fn = "../db/plaintext_index_bench_rearrange.json"
        self.serialized_index_bench_fn = "../db/serialized_index.json"
        self.serialized_index_map_bench_fn = "../db/serialized_index_map.json"
        self.dp_sse_pt = dp_sse.dp_sse_plaintext()
        
        self.db = []
        self.keyword_univ = []
        self.stop_words = []
        self.stop_words_map = defaultdict(bool)
        self.bucket_status = defaultdict()

        self.init_db()
        self.init_keyword_univ_and_stop_words()
        self.init_bucket_status()

    def init_db(self):
        with open(self.db_fn, 'r') as fd:
            self.db = json.load(fd)

    def init_keyword_univ_and_stop_words(self):
        with open( self.db_inverted_fn, 'r' ) as fd:
            db_inverted = json.load(fd)
            for keyword, ids in db_inverted:
                if len(ids) <= self.dp_sse_pt.cmax:
                    self.keyword_univ.append( keyword )
                else:
                    self.stop_words.append( keyword )
                    self.stop_words_map[keyword] = True

    def init_bucket_status(self):
        init_bucket_list = [0 for i in range( self.dp_sse_pt.cmax + 1 )]
        init_bucket_list[0] = sys.maxint
        for keyword in self.keyword_univ:
            self.bucket_status[ keyword ] = init_bucket_list[:]
        

    # Build index as in dpsse but all index are not FHIPPE encrypted yet.
    # Input:
    #   N/A 
    # Output:
    #   a list of (id, polynomial) pairs, output to a json file 
    ##
    def build_index_plain(self):
        pt_index = []
        for id in self.db.keys():
            keywords = self.db[id]
            pt_index.append(
                ( id, self.dp_sse_pt.gen_polynomial_plain( keywords, id ) )
            )
        with open( self.pt_index_fn, 'w+' ) as fd:
            json.dump( pt_index, fd )
    
    # Simulate Hash id into bucket using 2-hash choice
    # Input:
    #   id: string/integer 
    #   max_bucket: the number of bucket 
    #   bucket_status: a dict whose key is keyword, value is a list (self.cmax in total)
    #  of integers indicating the counter for that keyword in that bucket 
    # Output:
    #   bucket: int 
    #   counter: int 
    ## 
    def hash_choice(self, id, keyword, max_bucket):
        random.seed( time.time() )
        b1 = int( self.dp_sse_pt.hash_1( id ) )
        b2 = int( self.dp_sse_pt.hash_2( id ) )
        c1 = self.bucket_status[keyword][b1]
        c2 = self.bucket_status[keyword][b2]
        b = b1 
        if c2 < c1:
            b = b2 
        elif c1 == c2:
            if random.random() <= 0.5:
                b = b2 
        self.bucket_status[keyword][b] += 1
        return b, self.bucket_status[keyword][b]

    # Build logical index for benchmarking usage,
    # each sub-index for a file will be represented by a tuple 
    # (id, hash_1(id), hash_2(id), {(keyword, bucket, counter): True, ...})
    # where keywords is a list of keyword in such file 
    # Input:
    #   N/A 
    # Output:
    #   A list of (id, hash_1(id), hash_2(id), {(keyword, bucket, counter): True, ...}) tuples
    ##
    def build_index_plain_bench(self):
        pt_index_bench = []
        for id in self.db.keys():
            h1, h2 = int(self.dp_sse_pt.hash_1(id)), int( self.dp_sse_pt.hash_2(id) )
            keywords = self.db[id]
            term_map = defaultdict( bool )
            for keyword in keywords:
                if self.stop_words_map[keyword]: continue 
                bucket, counter = self.hash_choice( id, keyword, self.dp_sse_pt.cmax)
                term_map[str( (keyword, bucket, counter ) )] = True 
            pt_index_bench.append( (id, h1, h2, term_map) )
        return pt_index_bench 
    
    # Re-arrange pt_index_bench according to their hash_1, and hash_2 
    # Input: 
    #   pt_index_bench generated by build_index_plain_bench
    # Output:
    #   {bucket: [(id, term_map), (id, term_map)], ... }  
    # where bucket is integer
    ##
    def rearrange_pt_index_bench(self, pt_index_bench):
        pt_index_bench_rearrange = defaultdict( list )
        for pt_index in pt_index_bench:
            id, h1, h2, term_map = pt_index
            pt_index_bench_rearrange[ int(h1) ].append( (id, term_map) )
            pt_index_bench_rearrange[ int(h2) ].append( (id, term_map) )
        return pt_index_bench_rearrange
    
    # Simulate Search_plain in benchmarking
    # Input:
    #   idx: (id, term_map)
    #   token: term = (keyword, bucket, counter, id, dummy_or_not)
    #           
    # Output:
    #   True/False for a match
    #   id 
    #   keyword_match: match keyword or not 
    #   id_match: match id or not 
    ##
    def search_plain_bench(self, idx, token):
        if idx == None: return False, None, False, False
        id, term_map = idx 
        keyword, bucket, counter, id_in_token, dummy_or_not = token 
        if dummy_or_not: return False, None, False, False
        if id == id_in_token:
            return True, id, False, True 
        if term_map[ str((keyword, bucket, counter)) ]:
            return True, id, True, False
        return False, None, False, False 

    # Simulate Generate true positive basic tokens (unencrypted)
    # Input:
    #   keyword: string 
    #   tp: true positive rate per hash function
    # Note: tp and fp are not overall true positive rate or false positive rate. 
    # They are aligned with the notation in the paper.
    # Output:
    #   A list of terms where 
    #  each term = (keyword, bucket, counter, None, False)
    ## 
    def gen_tokens_tp_bench(self, keyword, tp):
        random.seed(time.time())
        tp_tokens = []
        for bucket in range(1, self.dp_sse_pt.cmax + 1):
            for counter in range(1, self.dp_sse_pt.countermax + 1):
                if random.random() <= tp:
                    tp_tokens.append( (keyword, bucket, counter, None, False) )
        return tp_tokens
    
    # Simulate Generate false positive basic tokens (unencrypted)
    # Input:
    #   fp: false positive rate per hash function
    # Note: tp and fp are not overall true positive rate or false positive rate. 
    # They are aligned with the notation in the paper.
    # Output:
    #   A list of terms where 
    #  each term = (None, None, None, id, False)
    ## 
    def gen_tokens_fp_bench(self, fp):
        random.seed(time.time())
        fp_tokens = []
        #for hash_1
        for id in range( 1, self.dp_sse_pt.new_db_size +1 ):
            if random.random() <= fp:
                bucket = int( self.dp_sse_pt.hash_1(id) )
                fp_tokens.append( (None, bucket, None, id, False) )
        # for hash_2
        for id in range( 1, self.dp_sse_pt.new_db_size + 1 ):
            if random.random() <= fp:
                bucket = int( self.dp_sse_pt.hash_2(id) )
                fp_tokens.append( (None, bucket, None, id, False) )
        
        return fp_tokens
    
    # Simulate Generate non-match basic tokens (unencrypted) 
    # Input:
    #   fp: false positive rate per hash function
    # Note: tp and fp are not overall true positive rate or false positive rate. 
    # They are aligned with the notation in the paper.
    # Output:
    #   A list of terms where 
    #  each term = (None, None, None, None, True)
    ## 
    def gen_tokens_non_match_bench(self, fp):
        random.seed(time.time())
        nm_tokens = []
        pool = [i for i in range(1, self.dp_sse_pt.new_db_size + 1)]
        while len(pool) > 0:
            tmp = []
            for id in pool: 
                if random.random() <= fp:
                    bucket = (int(id) % self.dp_sse_pt.cmax + 1 )
                    nm_tokens.append( (None, bucket, None, None, True) )
                    tmp.append(id)
            pool = tmp[:]
        return nm_tokens
    
    # Simulate all basic tokens (unencrypted) generation given a keyword 
    # Input:
    #   keyword : string 
    #   tp:  true positive rate 
    #   fp: false positive rate per hash function
    # Note: tp and fp are not overall true positive rate or false positive rate. 
    # They are aligned with the notation in the paper.
    # Output:
    #   A list of tokens for simulate benchmarking
    ## 
    def gen_tokens_bench(self, keyword, tp, fp):
        random.seed(time.time())
        tp_tokens, fp_tokens, nm_tokens = [], [], []
        tp_tokens = self.gen_tokens_tp_bench(keyword, tp)
        fp_tokens = self.gen_tokens_fp_bench(fp)
        nm_tokens = self.gen_tokens_non_match_bench(fp)
        all_tokens = tp_tokens + fp_tokens + nm_tokens
        return all_tokens 
    
    # Re-arrange all_tokens according to their bucket  
    # Input: 
    #   all_tokens: A list of tokens for simulate benchmarking, generated by self.gen_token_bench
    # Output:
    #   {bucket: [token, token], ... }  
    # where bucket is integer
    ##
    def rearrange_all_tokens_bench(self, all_tokens):
        rearrange_tokens = defaultdict(list)
        for token in all_tokens:
            bucket = token[1]
            rearrange_tokens[ int(bucket) ].append( token[:] )
        return rearrange_tokens

    # Serialize rearranged index or tokens 
    # Input:
    #   simulate_index/tokens: the rearranged_form generated from self.rearrange_all_tokens_bench/ self.rearrange_pt_index_bench
    # Output:
    #   a list of index/tokens,
    # and a map: token => its index of the list 
    ##
    def serialze_rearrange_bench(self, rearrange_form):
        serialized = []
        serialized_map = {}
        counter = 0
        for i in [ j + 1 for j in range(self.dp_sse_pt.cmax)  ]:
            terms = rearrange_form[i]
            for idx, term in enumerate(terms):
                serialized.append( term )
                serialized_map[ str(i) + "+" + str(idx)] = counter
                counter += 1
        return serialized, serialized_map

    # simulate one core to run sub task 
    # Input:
    #   serialized_index
    #   serialized_tokens
    #   computation_graph
    # Output:
    #   the number of simulate search_plain_bench called 
    ##
    def single_core_subtask_bench(self, serialized_index, serialized_tokens, comp_graph):
        count = 0
        query_result = []
        discard_index, discard_token = defaultdict(bool), defaultdict(bool)
        for idx_index, idx_token in comp_graph:
            if discard_index[idx_index] or discard_token[idx_token]:
                continue
            count += 1
            index = serialized_index[idx_index]
            token = serialized_tokens[idx_token]
            match, id, keyword_match, id_match =  self.search_plain_bench( index, token )
            if match:
                discard_index[idx_index] = True 
                discard_token[idx_token] + True 
                query_result.append( id )
        return query_result, count
    
    # Build computation graph to ease parallel computing 
    # Input:
    #   simulated_index, simulated_tokens: already rearrange
    #   serialized_map_index, serialized_map_tokens
    # Output:
    #   a list of (idx_index, idx_token) pairs for evaluting 
    ##
    def build_computation_graph_bench(self, simulated_index, simulated_tokens, serialized_map_index, serialized_map_tokens):
        computation_graph = []
        #Note bucket here is integer
        for bucket in [ i + 1 for i in range(self.dp_sse_pt.cmax)]:
            for idx_index, index in enumerate(simulated_index[str(bucket)]):
                for idx_token, token in enumerate(simulated_tokens[bucket]):
                    computation_graph.append( (
                        serialized_map_index[str(bucket) + "+" + str(idx_index)],
                        serialized_map_tokens[ str(bucket) + "+" + str( idx_token ) ]
                    ) )
        return computation_graph

    # Simulate one query process including
    # polynomial generation, token generation and match computing 
    # Input:
    #   serialized_index, serialized_tokens: generated from self.serialze_rearrange_bench
    #   serialized_map_index, serialized_map_tokens: the corresponding map for the serialized form above
    #   num_cores: the number of cpu cores for parallel computing 
    # Output:
    #   query_results: a list of returned doc ids 
    #   benchmarking_results: a list (of size num_cores) of integer the number of single_search evaluation for each core.
    ##
    def benchmarking_kernel(self, simulated_index, simulated_tokens, serialized_index, serialized_tokens, serialized_map_index, serialized_map_tokens, num_core):
        # A list of paird index in serialized_index and serialized_tokens to be evaluated
        computation_graph = self.build_computation_graph_bench( simulated_index, simulated_tokens, serialized_map_index, serialized_map_tokens )
        # separate the computation_graph into num_core parts and run simulation
        core_workload = len(computation_graph) / num_core + 1
        benchmarking_results = []
        query_results = []
        for core in range( num_core):
            begin, end = core * core_workload, (core+1) * core_workload
            sub_task = computation_graph[ begin : end ] #end not included
            query_result, comp_effort = self.single_core_subtask_bench( serialized_index, serialized_tokens, sub_task )
            query_results += query_result
            benchmarking_results.append( comp_effort )
        return query_results, benchmarking_results
    
    #doing similar things as benchmarking_kernel but only estimate the computation effort
    # It should be noted that the estimate computation effort here tend to be larger than the real computation efforts since in practice 
    #   1. if a file/index has already been matched by one token, there is no need for it to evaluate with other tokens
    #   2. if a token has matched one index/file, there is no need for that token to evaluate with other file/index
    #   3. The false positives generated from hash_1 ( hash_2 ) do not need to evaluate with index rearranged according to hash_2 (hash_1).

    def benchmarking_kernel_simple(self, simulated_index, simulated_tokens, serialized_map_index, serialized_map_tokens, num_core_list, time_per_eval):
        computation_graph = self.build_computation_graph_bench( simulated_index, simulated_tokens, serialized_map_index, serialized_map_tokens )
        tm = [round( len(computation_graph) / num_core * time_per_eval / 60, 2) for num_core in num_core_list ]
        return len(computation_graph), [
            "{} core, time: {} mins".format(num_core, t) for t in tm 
        ]


    # Created and store all index-related parameters including simulate_index (pt_index_bench_rearrange), and serialized_index, serialized_map_index
    # Input:
    #   N/A 
    # Output:
    #   N/A, all stored in ../db/ 
    ##
    def create_and_store_index_bench(self):
        pt_index_bench = self.build_index_plain_bench()
        pt_index_bench_rearrange = self.rearrange_pt_index_bench( pt_index_bench )
        serialized_index, serialized_map_index = self.serialze_rearrange_bench( pt_index_bench_rearrange )
        with open(self.pt_index_bench_fn, 'w') as fd:
            json.dump( pt_index_bench_rearrange, fd )
        
        with open(self.serialized_index_bench_fn, 'w') as fd:
            json.dump( serialized_index, fd )
        
        with open(self.serialized_index_map_bench_fn, 'w') as fd:
            json.dump( serialized_map_index, fd )
    
    # Load all index related parameter for benchmarking
    # Input:
    #   N/A 
    # Output:
    #   simulate_index (pt_index_bench_rearrange), and serialized_index, serialized_map_index
    def load_index_bench(self):
        simulated_index, serialized_index, serialized_map_index =[], [], []
        with open(self.pt_index_bench_fn, 'r') as fd:
            simulated_index = json.load(fd)
        
        with open(self.serialized_index_bench_fn, 'r') as fd:
            serialized_index = json.load(fd)
        
        with open(self.serialized_index_map_bench_fn, 'r') as fd:
            serialized_map_index = json.load(fd)
        return simulated_index, serialized_index, serialized_map_index
    

if __name__ == '__main__':
    dp_sse_bh = dp_sse_bench()
    # Already created 
    #dp_sse_bh.create_and_store_index_bench()
    
    simulated_index, serialized_index, serialized_map_index = dp_sse_bh.load_index_bench( )

    keyword = "test"
    tp, fp = 0.9999, 0.01
    all_tokens = dp_sse_bh.gen_tokens_bench(keyword, tp, fp)
    print(len( all_tokens ))
    num_core_list = [4, 8, 16, 32, 64, 128, 160]
    time_per_eval = 1.25
    rearranged_tokens = dp_sse_bh.rearrange_all_tokens_bench( all_tokens )
    _, serialized_map_tokens = dp_sse_bh.serialze_rearrange_bench( rearranged_tokens )

    print( dp_sse_bh.benchmarking_kernel_simple(simulated_index, rearranged_tokens, serialized_map_index, serialized_map_tokens, num_core_list, time_per_eval ))


