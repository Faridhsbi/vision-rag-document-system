from app.rag.schemas import QueryResponse, SourceMetadata


def test_query_response_requires_source_metadata():
    response = QueryResponse(
        answer="Tidak boleh.",
        sources=[
            SourceMetadata(
                chunk_id="doc_page_007_text",
                page=7,
                type="text",
                score=0.82,
                excerpt="Penagihan hanya dapat dilakukan pada pukul 08.00 sampai 20.00.",
            )
        ],
    )

    assert response.sources[0].page == 7
    assert response.sources[0].type == "text"
