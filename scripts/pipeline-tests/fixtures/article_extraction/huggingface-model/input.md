Collection 4 items • Updated
• 9

#
[
](#huihui-aihuihui-qwen35-35b-a3b-abliterated)
huihui-ai/Huihui-Qwen3.5-35B-A3B-abliterated

This is an uncensored version of [Qwen/Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) created with abliteration (see [remove-refusals-with-transformers](https://github.com/Sumandora/remove-refusals-with-transformers) to know more about it).
This is a crude, proof-of-concept implementation to remove refusals from an LLM model without using TransformerLens.

##
[
](#ollama)
ollama

Please use the latest version of [ollama v0.17.5](https://github.com/ollama/ollama/releases/tag/v0.17.5)

You can use [huihui_ai/qwen3.5-abliterated:35b](https://ollama.com/huihui_ai/qwen3.5-abliterated:35b) directly,

```
ollama run huihui_ai/qwen3.5-abliterated:35b
```


##
[
](#chat_template-vl-thinkjinja)
chat_template-vl-think.jinja

We have added a new file named [chat_template-vl-think.jinja](https://huggingface.co/huihui-ai/Huihui-Qwen3.5-35B-A3B-abliterated/blob/main/chat_template-vl-think.jinja), which comes from the path `huihui-ai/Huihui-Qwen3-VL-30B-A3B-Thinking-abliterated`

. This template file supports the think mode.

The new file chat_template-vl.jinja is more compatible with using Tool Calling in [llama-server](https://github.com/ggml-org/llama.cpp/releases),
especially when [opencode](https://github.com/anomalyco/opencode/releases) and [oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode/releases)is involved.

This will help prevent 500 error messages from occurring in the llama-server.

###
[
](#how-to-use-it)
How to use it

Add --chat-template-file /path/chat_template-vl-think.jinja after the llama-server command.

###
[
](#usage-warnings)
Usage Warnings

**Risk of Sensitive or Controversial Outputs**: This model’s safety filtering has been significantly reduced, potentially generating sensitive, controversial, or inappropriate content. Users should exercise caution and rigorously review generated outputs.**Not Suitable for All Audiences**: Due to limited content filtering, the model’s outputs may be inappropriate for public settings, underage users, or applications requiring high security.**Legal and Ethical Responsibilities**: Users must ensure their usage complies with local laws and ethical standards. Generated content may carry legal or ethical risks, and users are solely responsible for any consequences.**Research and Experimental Use**: It is recommended to use this model for research, testing, or controlled environments, avoiding direct use in production or public-facing commercial applications.**Monitoring and Review Recommendations**: Users are strongly advised to monitor model outputs in real-time and conduct manual reviews when necessary to prevent the dissemination of inappropriate content.**No Default Safety Guarantees**: Unlike standard models, this model has not undergone rigorous safety optimization. huihui.ai bears no responsibility for any consequences arising from its use.