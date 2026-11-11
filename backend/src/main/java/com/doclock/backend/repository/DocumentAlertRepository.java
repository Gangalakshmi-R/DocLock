package com.doclock.backend.repository;

import com.doclock.backend.entity.DocumentAlert;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentAlertRepository extends JpaRepository<DocumentAlert, Long> {
    void deleteByDocumentId(Long documentId);
}
