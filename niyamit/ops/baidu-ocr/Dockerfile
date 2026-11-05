# Experimental CPU runtime pinned to the Unlimited-OCR R-SWA support branch.
# Source: https://github.com/ggml-org/llama.cpp/pull/24975
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake curl ca-certificates libcurl4-openssl-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY llama-source.tar.gz /tmp/llama-source.tar.gz
RUN echo '5c17acc0daee511e6bf3846638fdcb393c31cfeb7a8b38d57740019e07adddf1  /tmp/llama-source.tar.gz' | sha256sum -c - && tar xzf /tmp/llama-source.tar.gz --strip-components=1 && rm /tmp/llama-source.tar.gz
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DLLAMA_CURL=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=ON && cmake --build build -j 4 --target llama-server
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libcurl4 ca-certificates && rm -rf /var/lib/apt/lists/* && useradd --uid 10002 --create-home ocr
COPY --from=build /src/build/bin/ /app/
ENV LD_LIBRARY_PATH=/app
USER ocr
ENTRYPOINT ["/app/llama-server"]
