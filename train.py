import torch
import torch.nn as nn
from torch.utils.data import random_split, DataLoader, Dataset
from pathlib import Path
from torch.utils.tensorboard import SummaryWriter

from datasets import load_dataset
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.trainers import WordLevelTrainer
from tokenizers.pre_tokenizers import Whitespace

from dataset import BilingualDataset
from model import build_transformer
from config import get_weights_file_path, get_config

def get_all_sentences(dataset, lang):
    """
    Generator function to extract sentences from a dataset for a specified language.

    Parameters:
        - dataset (List[Dict]): List of dictionary entries representing the dataset.
        - lang (str): Language key indicating the required language.

    Yields:
        - sentence (str): Extracted sentence for the specified language.
    """
    for item in dataset:
        yield item['translation'][lang]

def get_or_build_tokenizer(config, dataset, lang):
    """
    Retrieves an existing tokenizer or builds a new one for a specified language.

    Parameters:
        - config (Dict): Configuration dictionary containing tokenizer_file path.
        - dataset (List[Dict]): List of dictionary entries representing the dataset.
        - lang (str): Language key indicating the target language.

    Returns:
        - tokenizer (Tokenizer): Tokenizer object for the specified language.
    """
    tokenizer_path = Path(config['tokenizer_file'].format(lang))

    if not Path.exists(tokenizer_path):
        tokenizer = Tokenizer(WordLevel(unk_token='[UNK]'))
        tokenizer.pre_tokenizer = Whitespace()
        trainer = WordLevelTrainer(special_tokens = ['[UNK]', '[PAD]', '[SOS]', '[EOS]'])
        tokenizer.train_from_iterator(get_all_sentences(dataset, lang), trainer=trainer)
    else:
        tokenizer = Tokenizer.from_file(str(tokenizer_path))

    return tokenizer

def get_dataset(config):
    """
    Fetches and preprocesses opus_books bilingual dataset, creating dataloaders for training and validation.

    Parameters:
        - config (dict): Configuration parameters.

    Returns:
        - train_dataloader (DataLoader): Dataloader for training data.
        - validation_dataloader (DataLoader): Dataloader for validation data.
        - src_tokenizer (Tokenizer): Tokenizer for source language.
        - tgt_tokenizer (Tokenizer): Tokenizer for target language.
    """
    dataset_name = "opus_books"
    dataset = load_dataset(dataset_name, f'{config["src_lang"]}-{config["tgt_lang"]}', split='train')

    src_tokenizer = get_or_build_tokenizer(config, dataset, config["src_lang"])
    tgt_tokenizer = get_or_build_tokenizer(config, dataset, config["tgt_lang"])

    training_data_raw, validation_data_raw = random_split(dataset, [int(0.9*len(dataset)), len(dataset)-int(0.9*len(dataset))])

    training_data = BilingualDataset(training_data_raw, src_tokenizer, tgt_tokenizer, config["src_lang"], config["tgt_lang"], config["max_seq_len"])
    validation_data = BilingualDataset(validation_data_raw, src_tokenizer, tgt_tokenizer, config["src_lang"], config["tgt_lang"], config["max_seq_len"])

    max_src_len = 0
    max_tgt_len = 0

    for item in dataset:
        src_ids = src_tokenizer.encode(item["translation"][config["src_lang"]]).ids
        max_src_len = max(max_src_len, len(src_ids))
        tgt_ids = tgt_tokenizer.encode(item["translation"][config["tgt_lang"]]).ids
        max_tgt_len = max(max_tgt_len, len(tgt_ids))

    print(f'Max length of source sentence: {max_src_len}')
    print(f'Max length of target sentence: {max_tgt_len}')

    train_dataloader = DataLoader(training_data, batch_size=config["batch_size"], shuffle=True)
    validation_dataloader = DataLoader(training_data, batch_size=1, shuffle=True)

    return train_dataloader, validation_dataloader, src_tokenizer, tgt_tokenizer

def get_model(config, src_vocab_len, tgt_vocab_len):
    """
    Constructs and returns a transformer model based on the provided configuration and vocabulary lengths.

    Parameters:
        - config (dict): Configuration parameters.
        - src_vocab_len (int): Length of the source language vocabulary.
        - tgt_vocab_len (int): Length of the target language vocabulary.

    Returns:
        - model: Transformer model.
    """
    model = build_transformer(src_vocab_len, tgt_vocab_len, config["max_seq_len"], config["max_seq_len"], config["embedding_dim"])
    return model

def train_model(config):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    Path(config["model_folder"]).mkdir(parents=True, exist_ok=True)
    train_dataloader, validation_dataloader, src_tokenizer, tgt_tokenizer = get_dataset(config)
    model = get_model(config, src_tokenizer.get_vocab_size, tgt_tokenizer.get_vocab_size).to(device)

    writer = SummaryWriter(config["experiment_name"])

    optimizer = torch.optim.adam(model.parameters(), lr=config["learning_rate"], eps=1e-9)

    initial_epoch = 0
    global_step = 0

    if config["preload"]:
        model_filename = get_weights_file_path(config, config["preload"])
        print(f"Preloading Model: {model_filename}")
        state = torch.load(model_filename)
        # Work in Progress