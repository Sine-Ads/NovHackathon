"""tests/fixtures/mock_data.py — Mock response payloads for all data sources."""

MOCK_CLINICAL_TRIALS_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT04567890",
                    "briefTitle": "Gene Therapy Study for Severe Hemophilia A",
                    "officialTitle": "A Phase 3 Study of Valoctocogene Roxaparvovec in Hemophilia A",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "startDateStruct": {"date": "2023-04-15"},
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "BioMarin Pharmaceutical"}
                },
                "conditionsModule": {
                    "conditions": ["Hemophilia A", "Factor VIII Deficiency"]
                },
                "interventionsModule": {
                    "interventions": [{"name": "Valoctocogene Roxaparvovec", "type": "GENETIC"}]
                },
                "descriptionModule": {
                    "briefSummary": "Evaluating safety and efficacy of AAV5 gene therapy in severe hemophilia A.",
                    "detailedDescription": "Detailed Phase 3 clinical trial protocol description.",
                },
            }
        }
    ],
    "nextPageToken": None,
}

MOCK_PUBMED_ESEARCH_RESPONSE = {
    "esearchresult": {
        "count": "1",
        "retmax": "1",
        "retstart": "0",
        "querykey": "1",
        "webenv": "MCID_65f123456789abcdef",
        "idlist": ["38123456"],
    }
}

MOCK_PUBMED_EFETCH_XML = """<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2019//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_190101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
      <PMID Version="1">38123456</PMID>
      <Article PubModel="Print">
        <Journal>
          <JournalIssue CitedMedium="Internet">
            <Volume>390</Volume>
            <Issue>10</Issue>
            <PubDate>
              <Year>2024</Year>
              <Month>Jan</Month>
              <Day>15</Day>
            </PubDate>
          </JournalIssue>
          <Title>New England Journal of Medicine</Title>
          <ISOAbbreviation>N Engl J Med</ISOAbbreviation>
        </Journal>
        <ArticleTitle>Advances in Prophylactic Treatment for Haemophilia A</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Haemophilia A is an X-linked bleeding disorder.</AbstractText>
          <AbstractText Label="CONCLUSIONS">Non-factor therapies significantly reduce bleeding rates.</AbstractText>
        </Abstract>
        <AuthorList CompleteYN="Y">
          <Author ValidYN="Y">
            <LastName>Smith</LastName>
            <ForeName>John</ForeName>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading>
          <DescriptorName MajorTopicYN="Y">Hemophilia A</DescriptorName>
        </MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">38123456</ArticleId>
        <ArticleId IdType="doi">10.1056/NEJMoa2301234</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""

MOCK_OPENFDA_EVENTS_RESPONSE = {
    "results": [
        {
            "safetyreportid": "10023456",
            "receiptdate": "20231120",
            "serious": "1",
            "patient": {
                "drug": [
                    {
                        "medicinalproduct": "HEMLIBRA",
                        "drugindication": "HAEMOPHILIA A",
                    }
                ],
                "reaction": [
                    {"reactionmeddrapt": "Injection site reaction"}
                ],
            },
        }
    ]
}

MOCK_OPENFDA_RECALLS_RESPONSE = {
    "results": [
        {
            "recall_number": "D-0123-2024",
            "status": "Ongoing",
            "classification": "Class II",
            "product_description": "Antihemophilic Factor (Recombinant) 500 IU",
            "reason_for_recall": "Potential temperature excursion during shipping",
            "recalling_firm": "Takeda Pharma",
            "report_date": "20240210",
        }
    ]
}

MOCK_WHO_ICTRP_CSV = """TrialID,Public title,Scientific title,Recruitment status,Condition,Intervention,Primary sponsor,Date of registration,Countries
CTRI/2023/01/048123,Trial of FVII in Hemophilia,Evaluation of Recombinant FVII in Haemophilia A Patients,Recruiting,Haemophilia A,Recombinant Factor VII,AIIMS,15/01/2023,India
"""

MOCK_MEDRXIV_RESPONSE = {
    "messages": [{"status": "ok", "total": 1, "count": 1}],
    "collection": [
        {
            "doi": "10.1101/2024.01.15.24301234",
            "title": "Long-term Outcomes of Gene Therapy in Severe Hemophilia B",
            "abstract": "We report 5-year follow-up results in haemophilia B patients treated with AAV-FIX vectors.",
            "authors": "Doe J, Johnson M",
            "date": "2024-01-15",
            "version": "1",
            "category": "Hematology",
            "server": "medrxiv",
            "published": "NA",
        }
    ],
}

MOCK_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/2401.09876v1</id>
    <title>Deep Learning for PK Modeling in Haemophilia A Treatment</title>
    <summary>We propose a neural ODE framework to optimize Factor VIII dosing regimens in severe hemophilia.</summary>
    <published>2024-01-18T10:00:00Z</published>
    <author><name>Alan Turing</name></author>
    <arxiv:doi>10.1000/arxiv.2401.09876</arxiv:doi>
    <category term="q-bio.QM"/>
  </entry>
</feed>
"""

MOCK_USPTO_PATENTS_RESPONSE = {
    "response": {
        "numFound": 1,
        "docs": [
            {
                "patentApplicationNumber": "18123456",
                "inventionTitle": "Modified Factor VIII Molecules with Extended Half-Life",
                "abstractText": "Novel recombinant Factor VIII polypeptides for treatment of hemophilia A.",
                "filingDate": "2023-06-20",
                "grantDate": "2024-03-01",
                "applicantName": "BioGenetics Corp",
            }
        ],
    }
}

MOCK_SEC_EDGAR_RESPONSE = {
    "hits": {
        "total": {"value": 1, "relation": "eq"},
        "hits": [
            {
                "_id": "0001048268-24-000012:form10-k.htm",
                "_source": {
                    "adsh": "0001048268-24-000012",
                    "display_names": ["BIOMARIN PHARMACEUTICAL INC (CIK 0001048268)"],
                    "form": "10-K",
                    "file_date": "2024-02-28",
                    "period_ending": "2023-12-31",
                    "file_description": "ANNUAL REPORT",
                    "ciks": ["0001048268"],
                    "sics": ["2836"],
                },
                "highlight": {
                    "file_text": [
                        "Our commercial gene therapy for severe <em>hemophilia</em> A was approved..."
                    ]
                },
            }
        ],
    }
}
