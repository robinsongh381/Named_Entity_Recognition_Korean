from __future__ import absolute_import

import re
import argparse
import glob
from konlpy.tag import Kkma
import torch
import torch.nn as nn
from kobert.pytorch_kobert import get_pytorch_kobert_model
from kobert.utils import get_tokenizer
import gluonnlp as nlp
from tensorflow.keras.preprocessing.sequence import pad_sequences
from gluonnlp.data import SentencepieceTokenizer

from models.bert import KobertLSTMCRF, KobertCRF
from utils.data_loader import transform_to_bert_input
from utils.tokenizer import Tokenizer
from utils.log import logger, init_logger
from utils.ner_formatter import compute_found_ner, decoding_text_with_tag
import utils.constant as model_config
from transformers import DistilBertModel


device = model_config.device
kkma = Kkma()
pattern = re.compile('["\\‘’|\(\)\[\]\<\>`\']')

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')
        

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-model", default='bert-lstm-crf', type=str, choices=['bert-crf', 'bert-lstm-crf'])
    parser.add_argument("-model_path", type=str)
    parser.add_argument("-remove_special_char", default=True)
    args = parser.parse_args()
    
    # Temp
    # args.model_path = './result/layer_3_kobert_lstm_False_crf_batch_64_epoch_20/'
   
    # Distll
    kobert, vocab = get_pytorch_kobert_model()
    if '12' in args.model_path:
        is_distill=False
        kobert = kobert
    else:
        is_distill=True
        kobert = DistilBertModel.from_pretrained('monologg/distilkobert')
        
    # Model Architecture
    if 'lstm_True' in args.model_path:
        use_lstm = True
        model = KobertLSTMCRF(config=model_config, bert_model=kobert, distill=is_distill) 
    else:
        use_lstm = False 
        model = KobertCRF(config=model_config, bert_model=kobert, distill=is_distill)

    # Tokenizer
    _tok_path = get_tokenizer()
    _pretrained_tokenizer = nlp.data.BERTSPTokenizer(_tok_path, vocab, lower=False)
    tokenizer = Tokenizer(_pretrained_tokenizer)

    # Load Entity Dictionary, Train and Test data
    index_to_entity = torch.load('./data/processed_data/index_to_entity.pt')
      
    # Load saved model
    model_dict = model.state_dict()
    model_files = glob.glob(args.model_path+'*.pt')
    best_acc_model = sorted(model_files, key=lambda x: x[-6:-3], reverse=True)[0]
    print('Loading checkpoint from {}'.format(best_acc_model))
    print(' ')
    checkpoint = torch.load(best_acc_model)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    model.to(device)
      
    # Process input text
    while(True):
        text = input("[문장을 입력해주세요] ")
        if text=='quit' or text=='break' or text=='stop':
            break
        print('[Original Text]')
        print(text)
        print(' ')
        if args.remove_special_char:    
            # special_char_start_pos = [i.start() for i in pattern.finditer(text)]
            origianl_text = text
            text = re.sub('[:"\\‘’|\(\)\[\]\<\>`\']', '', text)
            text = text.replace('·',' ') # special case for ·
            if origianl_text != text:
                print('[Speical removed Text]')
                print(text)
                print(' ')

        tokenized_text = tokenizer(text)
        tokenized_idx_with_cls_sep = [tokenizer.token_to_cls_sep_idx(tokenized_text)]
        token_ids, valid_length, segment_ids = transform_to_bert_input(tokenized_idx_with_cls_sep)

        # model output
        list_of_pred_ids, confidence = model(token_ids, valid_length, segment_ids)
        pred_ner_tag = [index_to_entity[i] for i in list_of_pred_ids[0]] 
        assert len(tokenized_text)==len(pred_ner_tag)-2

        sentence_with_tag = decoding_text_with_tag(tokenized_text, pred_ner_tag)
        pred_ner_dictionary = compute_found_ner(sentence_with_tag, confidence)

        print('[Text with Entity]')
        print(sentence_with_tag)
        print(' ')
        print('[Found entities]')
        for i in pred_ner_dictionary:
            print(i)
            print(' ')
