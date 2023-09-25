import torch
import torch.nn as nn
from torch.utils.data import random_split

from datasets import load_dataset
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from tokenizers.trainers import WordLevelTrainer

from pathlib import Path

def get_sentences(dataset, lang):
    for entry in dataset:
        yield entry['translation'][lang]

def get_or_build_tokenizer(config, dataset, lang):
    tokenizer_path = Path(config['tokenizer_file'].format(lang))

    if not Path.exists(tokenizer_path):
        tokenizer = Tokenizer(WordLevel(unk_token='[UNK]'))
        tokenizer.pre_tokenizer = Whitespace()
        trainer = WordLevelTrainer(special_tokens=['[SOS]', '[UNK]', '[EOS]', '[PAD]'], min_frequency = 2)
        tokenizer.train_from_iterator(get_sentences(dataset, lang), trainer=trainer)
        tokenizer.save(str(tokenizer_path))
    else:
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
    
    return tokenizer

def get_dataset(config):
    dataset_name = 'opus_books'

    # Load specific dataset and split in into training and validation dataset
    dataset = load_dataset(dataset_name, f'{config["lang_src"]}-{config["lang_target"]}', split='train')
    training_dataset, validation_dataset = random_split(dataset, [int(0.9*len(dataset)), int(0.1*len(dataset))])

    # Build or get Tokenizer
    src_tokenizer = get_or_build_tokenizer(config, dataset, config["lang_src"])
    target_tokenizer = get_or_build_tokenizer(config, dataset, config["lang_target"])