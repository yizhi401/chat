
import openai

def read_from_file(file_path) -> str:
    with open(file_path, "r") as f:
        return f.read()


def parse_audio():
    # Note: you need to be using OpenAI Python v0.27.0 for the code below to work
    audio_file= open("audio.m4a", "rb")
    openai.api_key = read_from_file("../openai.key").strip()
    transcript = openai.Audio.transcribe("whisper-1", audio_file)
    parsed_str : str = transcript["text"]
    # print string with utf-8 format
    print(parsed_str.encode('utf-8').decode('utf-8'))

def main():
    parse_audio()


if __name__ == "__main__":
    main()
