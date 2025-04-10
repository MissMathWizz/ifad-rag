from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from fastapi.responses import JSONResponse
import vertexai
vertexai.init(project="ifad-rag-project", location="us-central1")

from rich import print as rich_print
from rich.markdown import Markdown as rich_Markdown
from IPython.display import Markdown, display
from vertexai.generative_models import (
    Content,
    GenerationConfig,
    GenerationResponse,
    GenerativeModel,
    HarmCategory,
    HarmBlockThreshold,
    Image,
    Part,
)
from vertexai.language_models import TextEmbeddingModel
from vertexai.vision_models import MultiModalEmbeddingModel

# utils/image_utils.pyS
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # fallback to 8080 for local dev
    uvicorn.run("main:app", host="0.0.0.0", port=port)

    
    
# GCS config
GCS_BUCKET = "ifad-lanzi-mrag-food"
TEXT_INDEX_BLOB = "faiss/faiss_text_index.bin"
TEXT_META_BLOB = "faiss/text_metadata_lookup.pkl"
IMAGE_INDEX_BLOB = "faiss/faiss_image_desc_index.bin"
IMAGE_META_BLOB = "faiss/image_desc_metadata_lookup.pkl"   
    
    
import faiss
import io
import pickle

# ========== FAISS Loader from GCS ========== #
import tempfile

def load_faiss_and_metadata_from_gcs(bucket_name, index_blob, metadata_blob):
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    index_bytes = bucket.blob(index_blob).download_as_bytes()
    with tempfile.NamedTemporaryFile(delete=False) as tmp_index_file:
        tmp_index_file.write(index_bytes)
        tmp_index_file.flush()
        index = faiss.read_index(tmp_index_file.name)
        
    metadata_bytes = bucket.blob(metadata_blob).download_as_bytes()
    metadata = pickle.loads(metadata_bytes)

    return index, metadata
    
import base64
from google.cloud import storage

def download_image_from_gcs(gcs_path: str, local_dir: str = "/tmp/images/") -> str:
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)
    
    # Parse bucket and blob
    if not gcs_path.startswith("gs://"):
        if gcs_path.startswith("/tmp/"):
            cleaned = gcs_path.replace("/tmp/", "").lstrip("/")
        else:
            cleaned = gcs_path.lstrip("/")
        gcs_path = f"gs://ifad-lanzi-mrag-food/{cleaned}"

    parts = gcs_path.replace("gs://", "").split("/", 1)
    bucket_name, blob_path = parts[0], parts[1]
    local_path = os.path.join(local_dir, os.path.basename(blob_path))
    
    # Skip if already downloaded
    if os.path.exists(local_path):
        return local_path

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)
    
    return local_path

def encode_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        encoded = base64.b64encode(img_file.read()).decode('utf-8')
    return encoded

# Multimodal models: Choose based on your performance/cost needs

multimodal_model_2_0_flash = GenerativeModel(
    "gemini-2.0-flash-001"
) # Gemini latest Gemini 2.0 Flash Model

multimodal_model_15 = GenerativeModel(
    "gemini-1.5-pro-001"
)  # works with text, code, images, video(with or without audio) and audio(mp3) with 1M input context - complex reasoning

# Multimodal models: Choose based on your performance/cost needs
multimodal_model_15_flash = GenerativeModel(
    "gemini-1.5-flash-001"
)  # works with text, code, images, video(with or without audio) and audio(mp3) with 1M input context - faster inference

# Load text embedding model from pre-trained source
text_embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")

# Load multimodal embedding model from pre-trained source
multimodal_embedding_model = MultiModalEmbeddingModel.from_pretrained(
    "multimodalembedding@001"
)  # works with image, image with caption(~32 words), video, video with caption(~32 words)

# ========== Load helper functions ========== #


# Parameters for Gemini API call.
# reference for parameters: https://cloud.google.com/vertex-ai/docs/generative-ai/model-reference/gemini

generation_config=  GenerationConfig(temperature=0.2, max_output_tokens=2048)

# Set the safety settings if Gemini is blocking your content or you are facing "ValueError("Content has no parts")" error or "Exception occured" in your data.
# ref for settings and thresholds: https://cloud.google.com/vertex-ai/docs/generative-ai/multimodal/configure-safety-attributes

safety_settings = {
                  HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                  HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                  HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                  HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                  }

# You can also pass parameters and safety_setting to "get_gemini_response" function
# Helper function
#@title Helper Functions

import glob
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from IPython.display import display
import PIL
from PIL import Image as PILImage, UnidentifiedImageError
import fitz
import numpy as np
import pandas as pd
import requests
from vertexai.generative_models import (
    GenerationConfig,
    HarmBlockThreshold,
    HarmCategory,
    Image,
)
from vertexai.vision_models import Image as vision_model_Image

# function to set embeddings as global variable

def set_global_variable(variable_name: str, value: any) -> None:
    """
    Sets the value of a global variable.

    Args:
        variable_name: The name of the global variable (as a string).
        value: The value to assign to the global variable. This can be of any type.
    """
    global_vars = globals()  # Get a dictionary of global variables
    global_vars[variable_name] = value




# Functions for getting text and image embeddings

def get_text_embedding_from_text_embedding_model(
    text: str,
    return_array: Optional[bool] = False,
) -> list:
    """
    Generates a numerical text embedding from a provided text input using a text embedding model.

    Args:
        text: The input text string to be embedded.
        return_array: If True, returns the embedding as a NumPy array.
                      If False, returns the embedding as a list. (Default: False)

    Returns:
        list or numpy.ndarray: A 768-dimensional vector representation of the input text.
                               The format (list or NumPy array) depends on the
                               value of the 'return_array' parameter.
    """
    embeddings = text_embedding_model.get_embeddings([text])
    text_embedding = [embedding.values for embedding in embeddings][0]

    if return_array:
        text_embedding = np.fromiter(text_embedding, dtype=float)

    # returns 768 dimensional array
    return text_embedding


def get_image_embedding_from_multimodal_embedding_model(
    image_uri: str,
    embedding_size: int = 512,
    text: Optional[str] = None,
    return_array: Optional[bool] = False,
) -> list:
    """Extracts an image embedding from a multimodal embedding model.
    The function can optionally utilize contextual text to refine the embedding.

    Args:
        image_uri (str): The URI (Uniform Resource Identifier) of the image to process.
        text (Optional[str]): Optional contextual text to guide the embedding generation. Defaults to "".
        embedding_size (int): The desired dimensionality of the output embedding. Defaults to 512.
        return_array (Optional[bool]): If True, returns the embedding as a NumPy array.
        Otherwise, returns a list. Defaults to False.

    Returns:
        list: A list containing the image embedding values. If `return_array` is True, returns a NumPy array instead.
    """
    # image = Image.load_from_file(image_uri)
    image = vision_model_Image.load_from_file(download_image_from_gcs(image_uri))
    embeddings = multimodal_embedding_model.get_embeddings(
        image=image, contextual_text=text, dimension=embedding_size
    )  # 128, 256, 512, 1408
    image_embedding = embeddings.image_embedding

    if return_array:
        image_embedding = np.fromiter(image_embedding, dtype=float)

    return image_embedding


def load_image_bytes(image_path):
    """Loads an image from a URL or local file path.

    Args:
        image_uri (str): URL or local file path to the image.

    Raises:
        ValueError: If `image_uri` is not provided.

    Returns:
        bytes: Image bytes.
    """
    # Check if the image_uri is provided
    if not image_path:
        raise ValueError("image_uri must be provided.")

    # Load the image from a weblink
    if image_path.startswith("http://") or image_path.startswith("https://"):
        response = requests.get(image_path, stream=True)
        if response.status_code == 200:
            return response.content

    # Load the image from a local path
    else:
        return open(image_path, "rb").read()


def get_pdf_doc_object(pdf_path: str) -> tuple[fitz.Document, int]:
    """
    Opens a PDF file using fitz.open() and returns the PDF document object and the number of pages.

    Args:
        pdf_path: The path to the PDF file.

    Returns:
        A tuple containing the `fitz.Document` object and the number of pages in the PDF.

    Raises:
        FileNotFoundError: If the provided PDF path is invalid.

    """

    # Open the PDF file
    doc: fitz.Document = fitz.open(pdf_path)

    # Get the number of pages in the PDF file
    num_pages: int = len(doc)

    return doc, num_pages


# Add colors to the print
class Color:
    """
    This class defines a set of color codes that can be used to print text in different colors.
    This will be used later to print citations and results to make outputs more readable.
    """

    PURPLE: str = "\033[95m"
    CYAN: str = "\033[96m"
    DARKCYAN: str = "\033[36m"
    BLUE: str = "\033[94m"
    GREEN: str = "\033[92m"
    YELLOW: str = "\033[93m"
    RED: str = "\033[91m"
    BOLD: str = "\033[1m"
    UNDERLINE: str = "\033[4m"
    END: str = "\033[0m"


def get_text_overlapping_chunk(
    text: str, character_limit: int = 1000, overlap: int = 100
) -> dict:
    """
    * Breaks a text document into chunks of a specified size, with an overlap between chunks to preserve context.
    * Takes a text document, character limit per chunk, and overlap between chunks as input.
    * Returns a dictionary where the keys are chunk numbers and the values are the corresponding text chunks.

    Args:
        text: The text document to be chunked.
        character_limit: Maximum characters per chunk (defaults to 1000).
        overlap: Number of overlapping characters between chunks (defaults to 100).

    Returns:
        A dictionary where keys are chunk numbers and values are the corresponding text chunks.

    Raises:
        ValueError: If `overlap` is greater than `character_limit`.

    """

    if overlap > character_limit:
        raise ValueError("Overlap cannot be larger than character limit.")

    # Initialize variables
    chunk_number = 1
    chunked_text_dict = {}

    # Iterate over text with the given limit and overlap
    for i in range(0, len(text), character_limit - overlap):
        end_index = min(i + character_limit, len(text))
        chunk = text[i:end_index]

        # Encode and decode for consistent encoding
        chunked_text_dict[chunk_number] = chunk.encode("ascii", "ignore").decode(
            "utf-8", "ignore"
        )

        # Increment chunk number
        chunk_number += 1

    return chunked_text_dict


def get_page_text_embedding(text_data: Union[dict, str]) -> dict:
    """
    * Generates embeddings for each text chunk using a specified embedding model.
    * Takes a dictionary of text chunks and an embedding size as input.
    * Returns a dictionary where the keys are chunk numbers and the values are the corresponding embeddings.

    Args:
        text_data: Either a dictionary of pre-chunked text or the entire page text.
        embedding_size: Size of the embedding vector (defaults to 128).

    Returns:
        A dictionary where keys are chunk numbers or "text_embedding" and values are the corresponding embeddings.

    """

    embeddings_dict = {}

    if not text_data:
        return embeddings_dict

    if isinstance(text_data, dict):
        # Process each chunk
        # print(text_data)
        for chunk_number, chunk_value in text_data.items():
            text_embd = get_text_embedding_from_text_embedding_model(text=chunk_value)
            embeddings_dict[chunk_number] = text_embd
    else:
        # Process the first 1000 characters of the page text
        text_embd = get_text_embedding_from_text_embedding_model(text=text_data)
        embeddings_dict["text_embedding"] = text_embd

    return embeddings_dict


def get_chunk_text_metadata(
    page: fitz.Page,
    character_limit: int = 1000,
    overlap: int = 100,
    embedding_size: int = 128,
) -> tuple[str, dict, dict, dict]:
    """
    * Extracts text from a given page object, chunks it, and generates embeddings for each chunk.
    * Takes a page object, character limit per chunk, overlap between chunks, and embedding size as input.
    * Returns the extracted text, the chunked text dictionary, and the chunk embeddings dictionary.

    Args:
        page: The fitz.Page object to process.
        character_limit: Maximum characters per chunk (defaults to 1000).
        overlap: Number of overlapping characters between chunks (defaults to 100).
        embedding_size: Size of the embedding vector (defaults to 128).

    Returns:
        A tuple containing:
            - Extracted page text as a string.
            - Dictionary of embeddings for the entire page text (key="text_embedding").
            - Dictionary of chunked text (key=chunk number, value=text chunk).
            - Dictionary of embeddings for each chunk (key=chunk number, value=embedding).

    Raises:
        ValueError: If `overlap` is greater than `character_limit`.

    """

    if overlap > character_limit:
        raise ValueError("Overlap cannot be larger than character limit.")

    # Extract text from the page
    text: str = page.get_text().encode("ascii", "ignore").decode("utf-8", "ignore")

    # Get whole-page text embeddings
    page_text_embeddings_dict: dict = get_page_text_embedding(text)

    # Chunk the text with the given limit and overlap
    chunked_text_dict: dict = get_text_overlapping_chunk(text, character_limit, overlap)
    # print(chunked_text_dict)

    # Get embeddings for the chunks
    chunk_embeddings_dict: dict = get_page_text_embedding(chunked_text_dict)
    # print(chunk_embeddings_dict)

    # Return all extracted data
    return text, page_text_embeddings_dict, chunked_text_dict, chunk_embeddings_dict



def get_image_for_gemini(
    doc: fitz.Document,
    image: tuple,
    image_no: int,
    image_save_dir: str,
    file_name: str,
    page_num: int,
):
    """
    Extracts an image from a PDF document, ensures it is in a compatible format (removes alpha & CMYK issues),
    saves it as PNG, and loads it as a PIL Image Object.
    """

    xref = image[0]
    pix = fitz.Pixmap(doc, xref)

    # Convert images with alpha (RGBA) or unsupported color spaces to RGB
    if pix.alpha:
        pix = fitz.Pixmap(fitz.csRGB, pix)  # Converts RGBA to RGB (removes transparency)
    elif pix.colorspace.n > 3:  # CMYK or other non-RGB colorspaces
        pix = fitz.Pixmap(fitz.csRGB, pix)

    # Ensure output directory exists
    os.makedirs(image_save_dir, exist_ok=True)

    # Save as PNG
    image_name = f"{image_save_dir}/{file_name}_image_{page_num}_{image_no}_{xref}.png"
    os.makedirs(image_save_dir, exist_ok=True)
    pix.save(image_name)

    image_for_gemini = Image.load_from_file(download_image_from_gcs(image_name))  # Load back for processing
    return image_for_gemini, image_name




def get_gemini_response(
    generative_multimodal_model,
    model_input: List[str],
    stream: bool = True,
    generation_config: Optional[GenerationConfig] = GenerationConfig(
        temperature=0.2, max_output_tokens=2048
    ),
    safety_settings: Optional[dict] = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    },
    print_exception: bool = False,
) -> str:
    """
    This function generates text in response to a list of model inputs.

    Args:
        model_input: A list of strings representing the inputs to the model.
        stream: Whether to generate the response in a streaming fashion (returning chunks of text at a time) or all at once. Defaults to False.

    Returns:
        The generated text as a string.
    """
    response = generative_multimodal_model.generate_content(
        model_input,
        generation_config=generation_config,
        stream=stream,
        safety_settings=safety_settings,
    )
    response_list = []

    for chunk in response:
        try:
            response_list.append(chunk.text)
        except Exception as e:
            if print_exception:
              print(
                  "Exception occurred while calling gemini. Something is blocked. Lower the safety thresholds [safety_settings: BLOCK_NONE ] if not already done. -----",
                  e,
              )
            else:
              print("Exception occurred while calling gemini. Something is blocked. Lower the safety thresholds [safety_settings: BLOCK_NONE ] if not already done. -----")
            response_list.append("**Something blocked.**")
            continue
    response = "".join(response_list)

    return response


def get_text_metadata_df(
    filename: str, text_metadata: Dict[Union[int, str], Dict]
) -> pd.DataFrame:
    """
    This function takes a filename and a text metadata dictionary as input,
    iterates over the text metadata dictionary and extracts the text, chunk text,
    and chunk embeddings for each page, creates a Pandas DataFrame with the
    extracted data, and returns it.

    Args:
        filename: The filename of the document.
        text_metadata: A dictionary containing the text metadata for each page.

    Returns:
        A Pandas DataFrame with the extracted text, chunk text, and chunk embeddings for each page.
    """

    final_data_text: List[Dict] = []

    for key, values in text_metadata.items():
        for chunk_number, chunk_text in values["chunked_text_dict"].items():
            data: Dict = {}
            data["file_name"] = filename
            data["page_num"] = int(key) + 1
            data["text"] = values["text"]
            data["text_embedding_page"] = values["page_text_embeddings"][
                "text_embedding"
            ]
            data["chunk_number"] = chunk_number
            data["chunk_text"] = chunk_text
            data["text_embedding_chunk"] = values["chunk_embeddings_dict"][chunk_number]

            final_data_text.append(data)

    return_df = pd.DataFrame(final_data_text)
    return_df = return_df.reset_index(drop=True)
    return return_df


def get_image_metadata_df(
    filename: str, image_metadata: Dict[Union[int, str], Dict]
) -> pd.DataFrame:
    """
    This function takes a filename and an image metadata dictionary as input,
    iterates over the image metadata dictionary and extracts the image path,
    image description, and image embeddings for each image, creates a Pandas
    DataFrame with the extracted data, and returns it.

    Args:
        filename: The filename of the document.
        image_metadata: A dictionary containing the image metadata for each page.

    Returns:
        A Pandas DataFrame with the extracted image path, image description, and image embeddings for each image.
    """

    final_data_image: List[Dict] = []
    for key, values in image_metadata.items():
        for _, image_values in values.items():
            data: Dict = {}
            data["file_name"] = filename
            data["page_num"] = int(key) + 1
            data["img_num"] = int(image_values["img_num"])
            data["img_path"] = image_values["img_path"]
            data["img_desc"] = image_values["img_desc"]
            # data["mm_embedding_from_text_desc_and_img"] = image_values[
            #     "mm_embedding_from_text_desc_and_img"
            # ]
            data["mm_embedding_from_img_only"] = image_values[
                "mm_embedding_from_img_only"
            ]
            data["text_embedding_from_image_description"] = image_values[
                "text_embedding_from_image_description"
            ]
            final_data_image.append(data)

    return_df = pd.DataFrame(final_data_image).dropna()
    return_df = return_df.reset_index(drop=True)
    return return_df


def get_document_metadata(
    generative_multimodal_model,
    pdf_folder_path: str,
    image_save_dir: str,
    image_description_prompt: str,
    embedding_size: int = 128,
    generation_config: Optional[GenerationConfig] = GenerationConfig(
        temperature=0.2, max_output_tokens=2048
    ),
    safety_settings: Optional[dict] = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    },
    add_sleep_after_page: bool = False,
    sleep_time_after_page: int = 2,
    add_sleep_after_document: bool = False,
    sleep_time_after_document: int = 2,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    This function takes a PDF path, an image save directory, an image description prompt, an embedding size, and a text embedding text limit as input.

    Args:
        pdf_path: The path to the PDF document.
        image_save_dir: The directory where extracted images should be saved.
        image_description_prompt: A prompt to guide Gemini for generating image descriptions.
        embedding_size: The dimensionality of the embedding vectors.
        text_emb_text_limit: The maximum number of tokens for text embedding.

    Returns:
        A tuple containing two DataFrames:
            * One DataFrame containing the extracted text metadata for each page of the PDF, including the page text, chunked text dictionaries, and chunk embedding dictionaries.
            * Another DataFrame containing the extracted image metadata for each image in the PDF, including the image path, image description, image embeddings (with and without context), and image description text embedding.
    """

    text_metadata_df_final, image_metadata_df_final = pd.DataFrame(), pd.DataFrame()

    for pdf_path in glob.glob(pdf_folder_path + "/*.pdf"):
        print(
            "\n\n",
            "Processing the file: ---------------------------------",
            pdf_path,
            "\n\n",
        )

        doc, num_pages = get_pdf_doc_object(pdf_path)

        file_name = pdf_path.split("/")[-1]

        text_metadata: Dict[Union[int, str], Dict] = {}
        image_metadata: Dict[Union[int, str], Dict] = {}

        for page_num in range(num_pages):
            print(f"Processing page: {page_num + 1}")

            page = doc[page_num]

            text = page.get_text()
            (
                text,
                page_text_embeddings_dict,
                chunked_text_dict,
                chunk_embeddings_dict,
            ) = get_chunk_text_metadata(page, embedding_size=embedding_size)

            text_metadata[page_num] = {
                "text": text,
                "page_text_embeddings": page_text_embeddings_dict,
                "chunked_text_dict": chunked_text_dict,
                "chunk_embeddings_dict": chunk_embeddings_dict,
            }

            images = page.get_images()
            image_metadata[page_num] = {}

            for image_no, image in enumerate(images):
                image_number = int(image_no + 1)
                image_metadata[page_num][image_number] = {}

                image_for_gemini, image_name = get_image_for_gemini(
                    doc, image, image_no, image_save_dir, file_name, page_num
                )

                print(
                    f"Extracting image from page: {page_num + 1}, saved as: {image_name}"
                )

                response = get_gemini_response(
                    generative_multimodal_model,
                    model_input=[image_description_prompt, image_for_gemini],
                    generation_config=generation_config,
                    safety_settings=safety_settings,
                    stream=True,
                )

                image_embedding = get_image_embedding_from_multimodal_embedding_model(
                    image_uri=image_name,
                    embedding_size=embedding_size,
                )

                image_description_text_embedding = (
                    get_text_embedding_from_text_embedding_model(text=response)
                )

                image_metadata[page_num][image_number] = {
                    "img_num": image_number,
                    "img_path": image_name,
                    "img_desc": response,
                    # "mm_embedding_from_text_desc_and_img": image_embedding_with_description,
                    "mm_embedding_from_img_only": image_embedding,
                    "text_embedding_from_image_description": image_description_text_embedding,
                }

            # Add sleep to reduce issues with Quota error on API
            if add_sleep_after_page:
                time.sleep(sleep_time_after_page)
                print(
                    "Sleeping for ",
                    sleep_time_after_page,
                    """ sec before processing the next page to avoid quota issues. You can disable it: "add_sleep_after_page = False"  """,
                )
        # Add sleep to reduce issues with Quota error on API
        if add_sleep_after_document:
            time.sleep(sleep_time_after_document)
            print(
                "\n \n Sleeping for ",
                sleep_time_after_document,
                """ sec before processing the next document to avoid quota issues. You can disable it: "add_sleep_after_document = False"  """,
            )

        text_metadata_df = get_text_metadata_df(file_name, text_metadata)
        image_metadata_df = get_image_metadata_df(file_name, image_metadata)

        text_metadata_df_final = pd.concat(
            [text_metadata_df_final, text_metadata_df], axis=0
        )
        image_metadata_df_final = pd.concat(
            [
                image_metadata_df_final,
                image_metadata_df.drop_duplicates(subset=["img_desc"]),
            ],
            axis=0,
        )

        text_metadata_df_final = text_metadata_df_final.reset_index(drop=True)
        image_metadata_df_final = image_metadata_df_final.reset_index(drop=True)

    return text_metadata_df_final, image_metadata_df_final


# Helper Functions


def get_user_query_text_embeddings(user_query: str) -> np.ndarray:
    """
    Extracts text embeddings for the user query using a text embedding model.

    Args:
        user_query: The user query text.
        embedding_size: The desired embedding size.

    Returns:
        A NumPy array representing the user query text embedding.
    """

    return get_text_embedding_from_text_embedding_model(user_query)


def get_user_query_image_embeddings(
    image_query_path: str, embedding_size: int
) -> np.ndarray:
    """
    Extracts image embeddings for the user query image using a multimodal embedding model.

    Args:
        image_query_path: The path to the user query image.
        embedding_size: The desired embedding size.

    Returns:
        A NumPy array representing the user query image embedding.
    """

    return get_image_embedding_from_multimodal_embedding_model(
        image_uri=image_query_path, embedding_size=embedding_size
    )


def get_cosine_score(
    dataframe: pd.DataFrame, column_name: str, input_text_embd: np.ndarray
) -> float:
    """
    Calculates the cosine similarity between the user query embedding and the dataframe embedding for a specific column.

    Args:
        dataframe: The pandas DataFrame containing the data to compare against.
        column_name: The name of the column containing the embeddings to compare with.
        input_text_embd: The NumPy array representing the user query embedding.

    Returns:
        The cosine similarity score (rounded to two decimal places) between the user query embedding and the dataframe embedding.
    """

    text_cosine_score = round(np.dot(dataframe[column_name], input_text_embd), 2)
    return text_cosine_score


def print_text_to_image_citation(
    final_images: Dict[int, Dict[str, Any]], print_top: bool = True
) -> None:
    """
    Prints a formatted citation for each matched image in a dictionary.

    Args:
        final_images: A dictionary containing information about matched images,
                    with keys as image number and values as dictionaries containing
                    image path, page number, page text, cosine similarity score, and image description.
        print_top: A boolean flag indicating whether to only print the first citation (True) or all citations (False).

    Returns:
        None (prints formatted citations to the console).
    """

    color = Color()

    # Iterate through the matched image citations
    for imageno, image_dict in final_images.items():
        # Print the citation header
        print(
            color.RED + f"Citation {imageno + 1}:",
            "Matched image path, page number and page text: \n" + color.END,
        )

        # Print the cosine similarity score
        print(color.BLUE + "score: " + color.END, image_dict["cosine_score"])

        # Print the file_name
        print(color.BLUE + "file_name: " + color.END, image_dict["file_name"])

        # Print the image path
        print(color.BLUE + "path: " + color.END, image_dict["img_path"])

        # Print the page number
        print(color.BLUE + "page number: " + color.END, image_dict["page_num"])

        # Print the page text
        print(
            color.BLUE + "page text: " + color.END, "\n".join(image_dict["page_text"])
        )

        # Print the image description
        print(
            color.BLUE + "image description: " + color.END,
            image_dict["image_description"],
        )

        # Only print the first citation if print_top is True
        if print_top and imageno == 0:
            break


def print_text_to_text_citation(
    final_text: Dict[int, Dict[str, Any]],
    print_top: bool = True,
    chunk_text: bool = True,
) -> None:
    """
    Prints a formatted citation for each matched text in a dictionary.

    Args:
        final_text: A dictionary containing information about matched text passages,
                    with keys as text number and values as dictionaries containing
                    page number, cosine similarity score, chunk number (optional),
                    chunk text (optional), and page text (optional).
        print_top: A boolean flag indicating whether to only print the first citation (True) or all citations (False).
        chunk_text: A boolean flag indicating whether to print individual text chunks (True) or the entire page text (False).

    Returns:
        None (prints formatted citations to the console).
    """

    color = Color()

    # Iterate through the matched text citations
    for textno, text_dict in final_text.items():
        # Print the citation header
        print(color.RED + f"Citation {textno + 1}:", "Matched text: \n" + color.END)

        # Print the cosine similarity score
        print(color.BLUE + "score: " + color.END, text_dict["cosine_score"])

        # Print the file_name
        print(color.BLUE + "file_name: " + color.END, text_dict["file_name"])

        # Print the page number
        print(color.BLUE + "page_number: " + color.END, text_dict["page_num"])

        # Print the matched text based on the chunk_text argument
        if chunk_text:
            # Print chunk number and chunk text
            print(color.BLUE + "chunk_number: " + color.END, text_dict["chunk_number"])
            print(color.BLUE + "chunk_text: " + color.END, text_dict["chunk_text"])
        else:
            # Print page text
            print(color.BLUE + "page text: " + color.END, text_dict["page_text"])

        # Only print the first citation if print_top is True
        if print_top and textno == 0:
            break


def get_similar_image_from_query(
    text_metadata_df: pd.DataFrame,
    image_metadata_df: pd.DataFrame,
    query: str = "",
    image_query_path: str = "",
    column_name: str = "",
    image_emb: bool = True,
    top_n: int = 3,
    embedding_size: int = 128,
) -> Dict[int, Dict[str, Any]]:
    """
    Finds the top N most similar images from a metadata DataFrame based on a text query or an image query.

    Args:
        text_metadata_df: A Pandas DataFrame containing text metadata associated with the images.
        image_metadata_df: A Pandas DataFrame containing image metadata (paths, descriptions, etc.).
        query: The text query used for finding similar images (if image_emb is False).
        image_query_path: The path to the image used for finding similar images (if image_emb is True).
        column_name: The column name in the image_metadata_df containing the image embeddings or captions.
        image_emb: Whether to use image embeddings (True) or text captions (False) for comparisons.
        top_n: The number of most similar images to return.
        embedding_size: The dimensionality of the image embeddings (only used if image_emb is True).

    Returns:
        A dictionary containing information about the top N most similar images, including cosine scores, image objects, paths, page numbers, text excerpts, and descriptions.
    """
    # Check if image embedding is used
    if image_emb:
        # Calculate cosine similarity between query image and metadata images
        user_query_image_embedding = get_user_query_image_embeddings(
            image_query_path, embedding_size
        )
        cosine_scores = image_metadata_df.apply(
            lambda x: get_cosine_score(x, column_name, user_query_image_embedding),
            axis=1,
        )
    else:
        # Calculate cosine similarity between query text and metadata image captions
        user_query_text_embedding = get_user_query_text_embeddings(query)
        cosine_scores = image_metadata_df.apply(
            lambda x: get_cosine_score(x, column_name, user_query_text_embedding),
            axis=1,
        )

    # Remove same image comparison score when user image is matched exactly with metadata image
    cosine_scores = cosine_scores[cosine_scores < 1.0]

    # Get top N cosine scores and their indices
    top_n_cosine_scores = cosine_scores.nlargest(top_n).index.tolist()
    top_n_cosine_values = cosine_scores.nlargest(top_n).values.tolist()

    # Create a dictionary to store matched images and their information
    final_images: Dict[int, Dict[str, Any]] = {}

    for matched_imageno, indexvalue in enumerate(top_n_cosine_scores):
        # Create a sub-dictionary for each matched image
        final_images[matched_imageno] = {}

        # Store cosine score
        final_images[matched_imageno]["cosine_score"] = top_n_cosine_values[
            matched_imageno
        ]

        # Load image from file
        final_images[matched_imageno]["image_object"] = Image.load_from_file(
            (download_image_from_gcs(image_metadata_df.iloc[indexvalue]["img_path"])))
        

        # Add file name
        final_images[matched_imageno]["file_name"] = image_metadata_df.iloc[indexvalue][
            "file_name"
        ]

        # Store image path
        final_images[matched_imageno]["img_path"] = image_metadata_df.iloc[indexvalue][
            "img_path"
        ]

        # Store page number
        final_images[matched_imageno]["page_num"] = image_metadata_df.iloc[indexvalue][
            "page_num"
        ]

        final_images[matched_imageno]["page_text"] = np.unique(
            text_metadata_df[
                (
                    text_metadata_df["page_num"].isin(
                        [final_images[matched_imageno]["page_num"]]
                    )
                )
                & (
                    text_metadata_df["file_name"].isin(
                        [final_images[matched_imageno]["file_name"]]
                    )
                )
            ]["text"].values
        )

        # Store image description
        final_images[matched_imageno]["image_description"] = image_metadata_df.iloc[
            indexvalue
        ]["img_desc"]

    return final_images


def get_similar_text_from_query(
    query: str,
    text_metadata_df: pd.DataFrame,
    column_name: str = "",
    top_n: int = 3,
    chunk_text: bool = True,
    print_citation: bool = False,
) -> Dict[int, Dict[str, Any]]:
    """
    Finds the top N most similar text passages from a metadata DataFrame based on a text query.

    Args:
        query: The text query used for finding similar passages.
        text_metadata_df: A Pandas DataFrame containing the text metadata to search.
        column_name: The column name in the text_metadata_df containing the text embeddings or text itself.
        top_n: The number of most similar text passages to return.
        embedding_size: The dimensionality of the text embeddings (only used if text embeddings are stored in the column specified by `column_name`).
        chunk_text: Whether to return individual text chunks (True) or the entire page text (False).
        print_citation: Whether to immediately print formatted citations for the matched text passages (True) or just return the dictionary (False).

    Returns:
        A dictionary containing information about the top N most similar text passages, including cosine scores, page numbers, chunk numbers (optional), and chunk text or page text (depending on `chunk_text`).

    Raises:
        KeyError: If the specified `column_name` is not present in the `text_metadata_df`.
    """

    if column_name not in text_metadata_df.columns:
        raise KeyError(f"Column '{column_name}' not found in the 'text_metadata_df'")

    query_vector = get_user_query_text_embeddings(query)

    # Calculate cosine similarity between query text and metadata text
    cosine_scores = text_metadata_df.apply(
        lambda row: get_cosine_score(
            row,
            column_name,
            query_vector,
        ),
        axis=1,
    )

    # Get top N cosine scores and their indices
    top_n_indices = cosine_scores.nlargest(top_n).index.tolist()
    top_n_scores = cosine_scores.nlargest(top_n).values.tolist()

    # Create a dictionary to store matched text and their information
    final_text: Dict[int, Dict[str, Any]] = {}

    for matched_textno, index in enumerate(top_n_indices):
        # Create a sub-dictionary for each matched text
        final_text[matched_textno] = {}

        # Store page number
        final_text[matched_textno]["file_name"] = text_metadata_df.iloc[index][
            "file_name"
        ]

        # Store page number
        final_text[matched_textno]["page_num"] = text_metadata_df.iloc[index][
            "page_num"
        ]

        # Store cosine score
        final_text[matched_textno]["cosine_score"] = top_n_scores[matched_textno]

        if chunk_text:
            # Store chunk number
            final_text[matched_textno]["chunk_number"] = text_metadata_df.iloc[index][
                "chunk_number"
            ]

            # Store chunk text
            final_text[matched_textno]["chunk_text"] = text_metadata_df["chunk_text"][
                index
            ]
        else:
            # Store page text
            final_text[matched_textno]["text"] = text_metadata_df["text"][index]

    # Optionally print citations immediately
    if print_citation:
        print_text_to_text_citation(final_text, chunk_text=chunk_text)

    return final_text


def display_images(
    images: Iterable[Union[str, PIL.Image.Image]], resize_ratio: float = 0.5
) -> None:
    """
    Displays a series of images provided as paths or PIL Image objects.

    Args:
        images: An iterable of image paths or PIL Image objects.
        resize_ratio: The factor by which to resize each image (default 0.5).

    Returns:
        None (displays images using IPython or Jupyter notebook).
    """

    # Convert paths to PIL images if necessary
    pil_images = []
    for image in images:
        if isinstance(image, str):
            pil_images.append(PIL.Image.open(image))
        else:
            pil_images.append(image)

    # Resize and display each image
    for img in pil_images:
        original_width, original_height = img.size
        new_width = int(original_width * resize_ratio)
        new_height = int(original_height * resize_ratio)
        resized_img = img.resize((new_width, new_height))
        display(resized_img)
        print("\n")

def get_answer_from_qa_system(
    query: str,
    text_metadata_df,
    image_metadata_df,
    top_n_text: int = 10,
    top_n_image: int = 5,
    instruction: Optional[str] = None,
    model=None,
    generation_config: Optional[GenerationConfig] = GenerationConfig(
        temperature=1, max_output_tokens=8192
    ),
    safety_settings: Optional[dict] = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    },
) -> Union[str, None]:
    """Fetches answers from a combined text and image-based QA system.

    Args:
        query (str): The user's question.
        text_metadata_df: DataFrame containing text embeddings, file names, and page numbers.
        image_metadata_df: DataFrame containing image embeddings, paths, and descriptions.
        top_n_text (int, optional): Number of top text chunks to consider. Defaults to 10.
        top_n_image (int, optional): Number of top images to consider. Defaults to 5.
        instruction (str, optional): Customized instruction for the model. Defaults to a generic one.
        model: Model to use for QA.
        safety_settings: Safety settings for the model.
        generation_config: Generation configuration for the model.

    Returns:
        Union[str, None]: The generated answer or None if an error occurs.
    """
    # Build Gemini content
    if instruction is None:  # Use default instruction if not provided
        instruction = """Task: Answer the following questions in detail, providing clear reasoning and evidence from the images and text in bullet points.
                      Instructions:

                      1. **Analyze:** Carefully examine the provided images and text context.
                      2. **Synthesize:** Integrate information from both the visual and textual elements.
                      3. **Reason:**  Deduce logical connections and inferences to address the question.
                      4. **Respond:** Provide a concise, accurate answer in the following format:

                        * **Question:** [Question]
                        * **Answer:** [Direct response to the question]
                        * **Explanation:** [Bullet-point reasoning steps if applicable]
                        * **Source** [name of the file, page, image from where the information is citied]

                      5. **Ambiguity:** If the context is insufficient to answer, respond "Not enough context to answer."

                      """

    # Retrieve relevant chunks of text based on the query
    matching_results_chunks_data = get_similar_text_from_query(
        query,
        text_metadata_df,
        column_name="text_embedding_chunk",
        top_n=top_n_text,
        chunk_text=True,
    )
    # Get all relevant images based on user query
    matching_results_image_fromdescription_data = get_similar_image_from_query(
        text_metadata_df,
        image_metadata_df,
        query=query,
        column_name="text_embedding_from_image_description",
        image_emb=False,
        top_n=top_n_image,
        embedding_size=1408,
    )

    # combine all the selected relevant text chunks
    context_text = ["Text Context: "]
    for key, value in matching_results_chunks_data.items():
        context_text.extend(
            [
                "Text Source: ",
                f"""file_name: "{value["file_name"]}" Page: "{value["page_num"]}""",
                "Text",
                value["chunk_text"],
            ]
        )

    # combine all the selected relevant images
    gemini_content = [
        instruction,
        "Questions: ",
        query,
        "Image Context: ",
    ]
    for key, value in matching_results_image_fromdescription_data.items():
        gemini_content.extend(
            [
                "Image Path: ",
                value["img_path"],
                "Image Description: ",
                value["image_description"],
                "Image:",
                value["image_object"],
            ]
        )
    gemini_content.extend(context_text)

    # Get Gemini response with streaming (if supported)
    response = get_gemini_response(
        model,
        model_input=gemini_content,
        stream=True,
        safety_settings=safety_settings,
        generation_config=generation_config,
    )

    return (
        response,
        matching_results_chunks_data,
        matching_results_image_fromdescription_data,
    )

# ========== Initialize FastAPI ========== #
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/healthz")
def health_check():
    return {"status": "ok"}

@app.get("/check-faiss")
def check_faiss():
    return {
        "text_index_dim": getattr(text_index, 'd', 'n/a'),
        "image_index_dim": getattr(image_index, 'd', 'n/a'),
        "text_metadata_count": len(text_metadata_lookup),
        "image_metadata_count": len(image_metadata_lookup)
    }

# ========== Load metadata (choose FAISS or Parquet) ========== #
USE_FAISS = True  # 🔁 Set to False if you want to fall back to pandas

if USE_FAISS:
    text_index, text_metadata_lookup = load_faiss_and_metadata_from_gcs(
        GCS_BUCKET, TEXT_INDEX_BLOB, TEXT_META_BLOB
    )
    image_index, image_metadata_lookup = load_faiss_and_metadata_from_gcs(
        GCS_BUCKET, IMAGE_INDEX_BLOB, IMAGE_META_BLOB
    )
else:
    # ⚠️ This uses more RAM — good for local, but not Cloud Run
    text_metadata_df = pd.read_parquet("merged_text_metadata.parquet")
    image_metadata_df = pd.read_parquet("merged_image_metadata.parquet")

# ========== Pydantic Schema ========== #
class Question(BaseModel):
    question: str

# ========== Main QA Endpoint ========== #
@app.post("/ask")
async def ask_q(q: Question):
    query = q.question

    # === FAISS-optimized text & image retrieval ===
    query_embedding = get_text_embedding_from_text_embedding_model(query)
    query_vector = np.array(query_embedding, dtype=np.float32).reshape(1, -1)

    # === Text retrieval from FAISS ===
    D_text, I_text = text_index.search(query_vector, k=10)
    matching_text = [text_metadata_lookup[i] for i in I_text[0]]

    # === Image retrieval from FAISS ===
    print("🧠 Query vector shape:", query_vector.shape)

    D_img, I_img = image_index.search(query_vector, k=5)
    matching_images = {i: image_metadata_lookup[i] for i in I_img[0]}

    # === Format prompt for Gemini ===
    instruction = """Task: Answer the following questions in detail, providing clear reasoning and evidence from the images and text in bullet points.

Instructions:
1. **Analyze** the provided images and text context.
2. **Synthesize** the visual and textual info.
3. **Reason** through the evidence.
4. **Respond** clearly and concisely.
5. **Cite sources** from filename, page, image.
6. If info is missing, say: 'Not enough context to answer.'"""

    context_text = ["Text Context:"]
    for match in matching_text:
        context_text.extend([
            "Text Source:",
            f"file_name: \"{match['file_name']}\" Page: \"{match['page_num']}\"",
            "Text:",
            match["chunk_text"],
        ])
        

    gemini_content = [instruction, "Questions:", query, "Image Context:"]
    
    # for _, match in matching_images.items():
    #     gemini_content.extend([
    #         "Image Path:", match["img_path"],
    #         "Image Description:", match["img_desc"],
    #         "Image:", Image.load_from_file(download_image_from_gcs(match["img_path"]))
    #     ])
    
    for _, match in matching_images.items():
        gcs_path = match["img_path"].rstrip(":")
        caption = match["img_desc"]

        try:
            local_path = download_image_from_gcs(gcs_path)

            # Validate with PIL
            with PILImage.open(local_path) as img:
                img.verify()
                img.load()

            # Gemini check
            gemini_img = Image.load_from_file(local_path)
            _ = gemini_img._mime_type  # Trigger internal check

            gemini_content.extend([
                "Image Path:", gcs_path,
                "Image Description:", caption,
                "Image:", gemini_img
            ])
            print(f"✅ Included in Gemini input | {gcs_path}")

        except Exception as e:
            print(f"❌ Skipped | {gcs_path} | {caption[:60]} | Reason: {e}")
            continue
    gemini_content.extend(context_text)

    response = get_gemini_response(
        generative_multimodal_model=multimodal_model_2_0_flash,
        model_input=gemini_content,
        generation_config=GenerationConfig(temperature=1, max_output_tokens=8192),
        safety_settings=safety_settings,
        stream=True,
    )

    # Convert matched images to base64 + captions
    images = []
    for _, image_data in matching_images.items():
        try:
            local_path = download_image_from_gcs(image_data["img_path"])
            base64_img = encode_image_base64(local_path)
            images.append({
                "caption": image_data["img_desc"],
                "base64": f"data:image/jpeg;base64,{base64_img}",
            })
        except Exception as e:
            print(f"Failed to process image: {e}")

    return {
        "question": query,
        "response": response,
        "images": images
    }

# 💡 new /faiss-test endpoint goes right below

from pydantic import BaseModel

class QueryVector(BaseModel):
    embedding: list
    modality: str  # "text" or "image"

@app.post("/faiss-test")
async def search_faiss(q: QueryVector):
    vector = np.array(q.embedding, dtype=np.float32).reshape(1, -1)
    modality = q.modality

    if modality == "text":
        D, I = text_index.search(vector, k=5)
        results = [text_metadata_lookup[i] for i in I[0]]
    elif modality == "image":
        D, I = image_index.search(vector, k=5)
        results = [image_metadata_lookup[i] for i in I[0]]
    else:
        return {"error": "Invalid modality: choose 'text' or 'image'"}

    return {"results": results}