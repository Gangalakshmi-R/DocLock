package com.doclock.backend.repository;

import com.doclock.backend.entity.DocumentFact;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentFactRepository extends JpaRepository<DocumentFact, Long> {
    void deleteByDocumentId(Long documentId);
}
